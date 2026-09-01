"""OnlyOfficeService — server-side ONLYOFFICE integration.

Responsibilities:
  * build the editor config and sign it with ONLYOFFICE_JWT_SECRET (server-side
    only — the browser never signs),
  * mint short-lived access tokens for the file/callback URLs,
  * validate and process the Document Server's save callbacks,
  * report health.

The document `key` is derived from the Approval Note version, so it changes on
every saved edit (ONLYOFFICE requires a fresh key when the document changes).
"""

from __future__ import annotations

import logging
import time
from urllib.parse import urlsplit, urlunsplit

import jwt

from app.core.config import settings
from app.models.approval_note import ApprovalNote
from app.models.user import User

logger = logging.getLogger(__name__)
_ALG = "HS256"

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class OnlyOfficeError(Exception):
    pass


class CallbackAuthError(OnlyOfficeError):
    pass


# --------------------------------------------------------------------------- #
# JWT / access tokens
# --------------------------------------------------------------------------- #
def _onlyoffice_secret() -> str:
    if not settings.onlyoffice_jwt_secret:
        raise OnlyOfficeError("ONLYOFFICE_JWT_SECRET is not configured.")
    return settings.onlyoffice_jwt_secret


def sign_config(payload: dict) -> str:
    """Sign the editor config so the Document Server accepts it (JWT enabled)."""
    return jwt.encode(payload, _onlyoffice_secret(), algorithm=_ALG)


def decode_onlyoffice_jwt(token: str) -> dict:
    return jwt.decode(token, _onlyoffice_secret(), algorithms=[_ALG])


def mint_access_token(note_id: int, purpose: str, *, ttl_seconds: int = 3600) -> str:
    """Short-lived token embedded in file/callback URLs (signed with our own
    app secret) so the Document Server can reach those endpoints without a user
    session, scoped to one note and purpose."""
    now = int(time.time())
    return jwt.encode(
        {"note_id": note_id, "purpose": purpose, "iat": now, "exp": now + ttl_seconds},
        settings.jwt_secret_key,
        algorithm=_ALG,
    )


def verify_access_token(token: str, purpose: str) -> int:
    try:
        claims = jwt.decode(token, settings.jwt_secret_key, algorithms=[_ALG])
    except jwt.InvalidTokenError as exc:
        raise CallbackAuthError("Invalid or expired access token.") from exc
    if claims.get("purpose") != purpose or "note_id" not in claims:
        raise CallbackAuthError("Access token scope mismatch.")
    return int(claims["note_id"])


# --------------------------------------------------------------------------- #
# Editor config
# --------------------------------------------------------------------------- #
def build_editor_config(note: ApprovalNote, user: User, *, mode: str = "edit") -> dict:
    base = settings.app_base_url_for_onlyoffice.rstrip("/")
    file_token = mint_access_token(note.id, "file")
    cb_token = mint_access_token(note.id, "callback")

    document = {
        "fileType": "docx",
        "key": note.onlyoffice_key,  # changes with document_version
        "title": f"{note.title}.docx",
        "url": f"{base}/api/onlyoffice/documents/{note.id}/file?token={file_token}",
        "permissions": {
            "download": True,
            "edit": mode == "edit",
            "print": True,
        },
    }
    editor_config = {
        "callbackUrl": f"{base}/api/onlyoffice/callback/{note.id}?token={cb_token}",
        "mode": "edit" if mode == "edit" else "view",
        "lang": "en",
        "user": {"id": str(user.id), "name": user.full_name},
        "coEditing": {"mode": "fast", "change": True},
        "customization": {
            "autosave": True,
            "forcesave": True,
        },
    }
    config = {
        "document": document,
        "documentType": "word",
        "editorConfig": editor_config,
        "height": "100%",
        "width": "100%",
    }
    # ONLYOFFICE requires the whole config signed when JWT is enabled.
    config["token"] = sign_config(config)
    return config


_COMMAND_ERRORS = {
    1: "The document is not open in ONLYOFFICE.",
    2: "The ONLYOFFICE callback URL is invalid.",
    3: "ONLYOFFICE could not save the document.",
    4: "No new changes are waiting to be saved.",
    5: "ONLYOFFICE rejected the save command.",
    6: "ONLYOFFICE rejected the command signature.",
}


def force_save(note: ApprovalNote, document_key: str) -> dict:
    """Ask the Document Server to persist the current in-editor state."""
    import httpx

    command = {
        "c": "forcesave",
        "key": document_key,
        "userdata": f"approval-note:{note.id}",
    }
    payload = {**command, "token": sign_config(command)}
    endpoint = f"{settings.onlyoffice_url.rstrip('/')}/command"
    try:
        with httpx.Client(timeout=settings.onlyoffice_request_timeout_seconds) as client:
            response = client.post(endpoint, json=payload)
            response.raise_for_status()
            result = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise OnlyOfficeError("Could not contact the ONLYOFFICE save service.") from exc

    error_code = int(result.get("error", 3))
    return {
        "accepted": error_code == 0,
        "error_code": error_code,
        "message": "Save requested." if error_code == 0 else _COMMAND_ERRORS.get(
            error_code, "ONLYOFFICE returned an unknown save error."
        ),
    }


# --------------------------------------------------------------------------- #
# Callback validation + processing
# --------------------------------------------------------------------------- #
def validate_callback(body: dict, authorization_header: str | None) -> dict:
    """Verify the callback's ONLYOFFICE JWT. The token may arrive in the body
    (`token`) or the Authorization header; both are checked."""
    token = body.get("token")
    if not token and authorization_header and authorization_header.lower().startswith("bearer "):
        token = authorization_header[7:]
    if not token:
        raise CallbackAuthError("Missing ONLYOFFICE callback token.")
    try:
        claims = decode_onlyoffice_jwt(token)
    except jwt.InvalidTokenError as exc:
        raise CallbackAuthError("Invalid ONLYOFFICE callback token.") from exc
    # ONLYOFFICE nests the callback payload under `payload` when signing headers.
    return claims.get("payload", claims)


def _rewrite_docserver_url(url: str) -> str:
    """Fetch the saved file from the browser-facing ONLYOFFICE origin.

    The Document Server hands back a URL using its own (often Docker-internal)
    host, which the backend may not resolve. Rewriting the scheme+host to
    ONLYOFFICE_URL keeps the path and reaches the same cache file.
    """
    onlyoffice = urlsplit(settings.onlyoffice_url.rstrip("/"))
    parts = urlsplit(url)
    return urlunsplit((onlyoffice.scheme, onlyoffice.netloc, parts.path, parts.query, parts.fragment))


def download_saved_file(url: str) -> bytes:
    import httpx

    fetch_url = _rewrite_docserver_url(url)
    with httpx.Client(timeout=settings.onlyoffice_request_timeout_seconds) as client:
        resp = client.get(fetch_url)
        resp.raise_for_status()
        return resp.content


def process_callback(db, note: ApprovalNote, payload: dict) -> dict:
    """Handle an ONLYOFFICE save callback. Returns the required ack body.

    Statuses: 1 editing · 2 ready-to-save · 3 save error · 4 closed-no-changes
              6 force-save · 7 force-save error.
    """
    from app.services import approval_note_service

    status = int(payload.get("status", 0))
    if status in (2, 6):  # a saveable version is available
        url = payload.get("url")
        if not url:
            logger.error("ONLYOFFICE callback status=%s without url (note %s)", status, note.id)
            return {"error": 1}
        try:
            data = download_saved_file(url)
            approval_note_service.save_new_version(
                db, note, data, last_editor_id=_last_editor(payload)
            )
        except Exception:  # noqa: BLE001 - never lose the current version on failure
            logger.exception("Failed to save ONLYOFFICE version for note %s", note.id)
            return {"error": 1}
        return {"error": 0}
    if status in (3, 7):  # save error reported by the Document Server
        logger.error("ONLYOFFICE reported save error status=%s for note %s", status, note.id)
        return {"error": 0}
    # 1 (editing) / 4 (closed, no changes) / others: just acknowledge.
    return {"error": 0}


def _last_editor(payload: dict) -> int | None:
    users = payload.get("users") or []
    try:
        return int(users[0]) if users else None
    except (ValueError, TypeError):
        return None


# --------------------------------------------------------------------------- #
# Health
# --------------------------------------------------------------------------- #
def check_health() -> dict:
    configured = bool(settings.onlyoffice_url and settings.onlyoffice_jwt_secret)
    reachable = False
    if configured:
        import httpx

        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(f"{settings.onlyoffice_url.rstrip('/')}/healthcheck")
                reachable = resp.status_code == 200 and "true" in resp.text.lower()
        except Exception:  # noqa: BLE001
            reachable = False
    return {"configured": configured, "reachable": reachable}
