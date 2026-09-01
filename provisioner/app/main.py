"""Provisioner control API and authenticated browser gateway for OpenHands."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import secrets
import sqlite3
import threading
import time
from contextlib import asynccontextmanager
from typing import Annotated, Any, Literal
from urllib.parse import parse_qsl, urlencode

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, WebSocket
from fastapi.responses import JSONResponse, RedirectResponse, Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from websockets.asyncio.client import connect as websocket_connect
from websockets.exceptions import ConnectionClosed

from app.config import Settings
from app.database import Database, WorkspaceRecord
from app.runtime import DockerRuntime


GATEWAY_BACKEND_KEY = "sih-gateway-managed-backend-key"
HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


class Identity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1, max_length=128)
    department_id: int | None = None
    department_scope: str | None = Field(default=None, max_length=128)
    role: str = Field(min_length=1, max_length=64)


class WorkspaceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Literal["openhands"]
    workspace_key: str = Field(pattern=r"^[A-Za-z0-9._-]{3,128}$")
    identity: Identity


class WorkspaceResponse(BaseModel):
    workspace_id: str
    status: Literal["provisioning", "ready"]
    launch_url: str | None = None


class LaunchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identity: Identity


class LaunchResponse(BaseModel):
    launch_url: str


class ProvisioningCoordinator:
    def __init__(self, database: Database, runtime: DockerRuntime):
        self.database = database
        self.runtime = runtime
        self._active: set[str] = set()
        self._lock = threading.Lock()

    def schedule(self, workspace: WorkspaceRecord) -> bool:
        with self._lock:
            if workspace.workspace_id in self._active:
                return False
            self._active.add(workspace.workspace_id)
        self.database.update_status(workspace.workspace_id, "provisioning")
        thread = threading.Thread(
            target=self._run,
            args=(workspace,),
            name=f"provision-{workspace.workspace_id}",
            daemon=True,
        )
        thread.start()
        return True

    def _run(self, workspace: WorkspaceRecord) -> None:
        try:
            self.runtime.ensure_workspace(workspace)
            self.database.update_status(workspace.workspace_id, "ready")
        except Exception as exc:  # The control API reports a retryable provisioning state.
            self.database.update_status(workspace.workspace_id, "provisioning", str(exc)[:500])
        finally:
            with self._lock:
                self._active.discard(workspace.workspace_id)


def _workspace_id(workspace_key: str) -> str:
    digest = hashlib.sha256(workspace_key.encode("utf-8")).hexdigest()[:20]
    return f"oh-{digest}"


def _container_name(workspace_id: str) -> str:
    return f"sih-openhands-{workspace_id}"


def _identity_dict(identity: Identity) -> dict[str, Any]:
    return identity.model_dump(mode="json")


def _rewrite_query(query: str, backend_key: str) -> str:
    if not query:
        return ""
    pairs = parse_qsl(query, keep_blank_values=True)
    rewritten = [
        (key, backend_key if value == GATEWAY_BACKEND_KEY else value)
        for key, value in pairs
    ]
    return urlencode(rewritten, doseq=True)


def _proxy_request_headers(request: Request, backend_key: str) -> dict[str, str]:
    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower()
        not in HOP_BY_HOP_HEADERS
        | {"host", "content-length", "cookie", "authorization", "accept-encoding"}
    }
    headers["X-Session-API-Key"] = backend_key
    headers["X-Forwarded-Host"] = request.headers.get("host", "")
    headers["X-Forwarded-Proto"] = request.url.scheme
    return headers


def _proxy_response_headers(headers: httpx.Headers, *, public_url: str, internal_url: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in headers.items():
        lowered = key.lower()
        if lowered in HOP_BY_HOP_HEADERS | {"content-length", "content-encoding"}:
            continue
        if lowered == "location":
            value = value.replace(internal_url, public_url)
        result[key] = value
    result["Cache-Control"] = "no-store"
    result["Referrer-Policy"] = "no-referrer"
    return result


async def _scrubbed_stream(upstream: httpx.Response, client: httpx.AsyncClient, secret: bytes):
    keep = max(len(secret) - 1, 0)
    carry = b""
    replacement = GATEWAY_BACKEND_KEY.encode("utf-8")
    try:
        async for chunk in upstream.aiter_bytes():
            data = carry + chunk
            if keep and len(data) > keep:
                emit, carry = data[:-keep], data[-keep:]
                yield emit.replace(secret, replacement)
            elif not keep:
                yield data.replace(secret, replacement)
                carry = b""
            else:
                carry = data
        if carry:
            yield carry.replace(secret, replacement)
    finally:
        await upstream.aclose()
        await client.aclose()


def create_app(
    settings: Settings | None = None,
    *,
    database: Database | None = None,
    runtime: DockerRuntime | None = None,
) -> FastAPI:
    settings = settings or Settings()
    database = database or Database(settings.database_path)
    runtime = runtime or DockerRuntime(settings)
    coordinator = ProvisioningCoordinator(database, runtime)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        database.cleanup_expired()
        for workspace in database.list_workspaces():
            if not runtime.is_ready(workspace):
                coordinator.schedule(workspace)
        yield

    app = FastAPI(
        title="SIH OpenHands Local Provisioner",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.database = database
    app.state.runtime = runtime
    app.state.coordinator = coordinator

    def require_control_api(
        authorization: Annotated[str | None, Header()] = None,
    ) -> None:
        scheme, _, supplied = (authorization or "").partition(" ")
        if scheme.lower() != "bearer" or not hmac.compare_digest(
            supplied, settings.provisioner_api_key
        ):
            raise HTTPException(
                status_code=401,
                detail="Invalid provisioner credentials.",
                headers={"WWW-Authenticate": "Bearer"},
            )

    def response_for(workspace: WorkspaceRecord) -> WorkspaceResponse:
        ready = workspace.status == "ready"
        return WorkspaceResponse(
            workspace_id=workspace.workspace_id,
            status="ready" if ready else "provisioning",
            launch_url=f"{settings.public_url}/canvas" if ready else None,
        )

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/workspaces", response_model=WorkspaceResponse)
    def ensure_workspace(
        payload: WorkspaceRequest,
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
        _control_api: None = Depends(require_control_api),
    ) -> WorkspaceResponse:
        expected_key = f"openhands-user-{payload.identity.user_id}"
        if not hmac.compare_digest(idempotency_key, expected_key):
            raise HTTPException(status_code=409, detail="Idempotency key does not match the user.")

        workspace = database.get_workspace_by_key(payload.workspace_key)
        by_user = database.get_workspace_by_user(payload.identity.user_id)
        if workspace is not None and workspace.user_id != payload.identity.user_id:
            raise HTTPException(status_code=409, detail="Workspace key belongs to another user.")
        if by_user is not None and by_user.workspace_key != payload.workspace_key:
            raise HTTPException(status_code=409, detail="User already owns another workspace.")

        if workspace is None:
            workspace_id = _workspace_id(payload.workspace_key)
            try:
                workspace = database.create_workspace(
                    workspace_id=workspace_id,
                    workspace_key=payload.workspace_key,
                    user_id=payload.identity.user_id,
                    identity=_identity_dict(payload.identity),
                    container_name=_container_name(workspace_id),
                    backend_api_key=secrets.token_urlsafe(32),
                )
            except sqlite3.IntegrityError:
                workspace = database.get_workspace_by_key(payload.workspace_key)
                if workspace is None or workspace.user_id != payload.identity.user_id:
                    raise HTTPException(status_code=409, detail="Workspace ownership conflict.")
        else:
            database.update_identity(workspace.workspace_id, _identity_dict(payload.identity))

        if runtime.is_ready(workspace):
            database.update_status(workspace.workspace_id, "ready")
        else:
            coordinator.schedule(workspace)
        refreshed = database.get_workspace(workspace.workspace_id)
        if refreshed is None:
            raise HTTPException(status_code=500, detail="Workspace state was lost.")
        return response_for(refreshed)

    @app.post("/v1/workspaces/{workspace_id}/launch", response_model=LaunchResponse)
    def launch_workspace(
        workspace_id: str,
        payload: LaunchRequest,
        response: Response,
        _control_api: None = Depends(require_control_api),
    ) -> LaunchResponse:
        workspace = database.get_workspace(workspace_id)
        if workspace is None:
            raise HTTPException(status_code=404, detail="Workspace was not found.")
        if workspace.user_id != payload.identity.user_id:
            raise HTTPException(status_code=403, detail="Workspace does not belong to this user.")
        if workspace.status != "ready" or not runtime.is_ready(workspace):
            database.update_status(workspace.workspace_id, "provisioning")
            coordinator.schedule(workspace)
            raise HTTPException(status_code=409, detail="Workspace is still provisioning.")

        database.update_identity(workspace.workspace_id, _identity_dict(payload.identity))
        ticket = secrets.token_urlsafe(32)
        database.create_launch_ticket(
            token=ticket,
            workspace_id=workspace.workspace_id,
            user_id=workspace.user_id,
            expires_at=int(time.time()) + settings.launch_ticket_ttl_seconds,
        )
        response.headers["Cache-Control"] = "no-store"
        return LaunchResponse(launch_url=f"{settings.public_url}/handoff?{urlencode({'ticket': ticket})}")

    @app.get("/handoff")
    def consume_handoff(ticket: Annotated[str, Query(min_length=20)]) -> Response:
        session_token = secrets.token_urlsafe(32)
        workspace = database.consume_launch_ticket(
            ticket=ticket,
            session_token=session_token,
            session_expires_at=int(time.time()) + settings.browser_session_ttl_seconds,
        )
        if workspace is None:
            return JSONResponse(
                status_code=401,
                content={"detail": "This launch link is invalid, expired, or already used."},
                headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
            )
        response = RedirectResponse(url="/canvas", status_code=303)
        response.set_cookie(
            settings.session_cookie_name,
            session_token,
            max_age=settings.browser_session_ttl_seconds,
            httponly=True,
            secure=settings.secure_cookie,
            samesite="lax",
            path="/",
        )
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    def workspace_for_cookie(cookie_value: str | None) -> WorkspaceRecord:
        if not cookie_value:
            raise HTTPException(status_code=401, detail="OpenHands launch session required.")
        workspace = database.resolve_session(cookie_value)
        if workspace is None:
            raise HTTPException(status_code=401, detail="OpenHands launch session expired.")
        return workspace

    @app.api_route(
        "/{path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    )
    async def proxy_http(path: str, request: Request) -> Response:
        workspace = workspace_for_cookie(request.cookies.get(settings.session_cookie_name))
        internal_url = f"http://{workspace.container_name}:8000"
        query = _rewrite_query(request.url.query, workspace.backend_api_key)
        upstream_url = f"{internal_url}/{path}"
        if query:
            upstream_url = f"{upstream_url}?{query}"
        body = await request.body()
        client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.proxy_timeout_seconds, connect=10.0),
            follow_redirects=False,
        )
        upstream_request = client.build_request(
            request.method,
            upstream_url,
            headers=_proxy_request_headers(request, workspace.backend_api_key),
            content=body,
        )
        try:
            upstream = await client.send(upstream_request, stream=True)
        except httpx.HTTPError:
            await client.aclose()
            return JSONResponse(status_code=502, content={"detail": "OpenHands is unavailable."})

        response_headers = _proxy_response_headers(
            upstream.headers,
            public_url=settings.public_url,
            internal_url=internal_url,
        )
        content_type = upstream.headers.get("content-type", "")
        secret = workspace.backend_api_key.encode("utf-8")
        if content_type.startswith("text/event-stream"):
            return StreamingResponse(
                _scrubbed_stream(upstream, client, secret),
                status_code=upstream.status_code,
                headers=response_headers,
                media_type="text/event-stream",
            )
        try:
            content = (await upstream.aread()).replace(
                secret, GATEWAY_BACKEND_KEY.encode("utf-8")
            )
        finally:
            await upstream.aclose()
            await client.aclose()
        return Response(
            content=content,
            status_code=upstream.status_code,
            headers=response_headers,
        )

    @app.websocket("/{path:path}")
    async def proxy_websocket(path: str, websocket: WebSocket) -> None:
        workspace = database.resolve_session(
            websocket.cookies.get(settings.session_cookie_name, "")
        )
        if workspace is None:
            await websocket.close(code=4401)
            return
        query = _rewrite_query(websocket.url.query, workspace.backend_api_key)
        upstream_url = f"ws://{workspace.container_name}:8000/{path}"
        if query:
            upstream_url = f"{upstream_url}?{query}"
        requested_protocols = [
            value.strip()
            for value in websocket.headers.get("sec-websocket-protocol", "").split(",")
            if value.strip()
        ]
        try:
            async with websocket_connect(
                upstream_url,
                additional_headers={"X-Session-API-Key": workspace.backend_api_key},
                subprotocols=requested_protocols or None,
                max_size=None,
            ) as upstream:
                await websocket.accept(subprotocol=upstream.subprotocol)
                secret = workspace.backend_api_key.encode("utf-8")
                replacement = GATEWAY_BACKEND_KEY.encode("utf-8")

                async def browser_to_upstream() -> None:
                    while True:
                        message = await websocket.receive()
                        if message["type"] == "websocket.disconnect":
                            return
                        if message.get("text") is not None:
                            await upstream.send(
                                message["text"].replace(GATEWAY_BACKEND_KEY, workspace.backend_api_key)
                            )
                        elif message.get("bytes") is not None:
                            await upstream.send(message["bytes"].replace(replacement, secret))

                async def upstream_to_browser() -> None:
                    while True:
                        message = await upstream.recv()
                        if isinstance(message, str):
                            await websocket.send_text(
                                message.replace(workspace.backend_api_key, GATEWAY_BACKEND_KEY)
                            )
                        else:
                            await websocket.send_bytes(message.replace(secret, replacement))

                tasks = {
                    asyncio.create_task(browser_to_upstream()),
                    asyncio.create_task(upstream_to_browser()),
                }
                done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in pending:
                    task.cancel()
                await asyncio.gather(*done, *pending, return_exceptions=True)
        except (ConnectionClosed, OSError, httpx.HTTPError):
            try:
                await websocket.close(code=1011)
            except RuntimeError:
                pass

    return app


app = create_app()
