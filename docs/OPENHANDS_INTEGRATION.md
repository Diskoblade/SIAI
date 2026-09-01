# OpenHands per-user coding workspaces

The portal integrates with the current OpenHands architecture: **Agent Canvas**
is the browser UI and **Agent Server** runs conversations, tools, terminals, and
workspace access. Agent Server is a code-execution boundary, so the portal does
not send all users to one unrestricted runtime or expose its session API key.

## Deployment shape

```text
Portal user
  -> authenticated POST /api/ide/workspaces
  -> portal backend (trusted identity and authorization)
  -> internal OpenHands provisioner
  -> one isolated workspace/runtime for that user
  -> identity-aware Agent Canvas gateway
```

The provisioner is infrastructure-owned. In Kubernetes it can create one pod
and PVC per user; with Docker it can create one restricted container and volume
per user. It must apply CPU/memory quotas, network policy, repository policy,
and an allowlisted Agent Server image. Do not mount the host Docker socket into
user runtimes or run Agent Server directly on a shared host filesystem.

## Portal configuration

```bash
OPENHANDS_ENABLED=true
OPENHANDS_PROVISIONER_URL=https://openhands-control.internal
OPENHANDS_PROVISIONER_API_KEY=<backend-only secret>
OPENHANDS_PUBLIC_URL=https://code.example.gov.in
OPENHANDS_REQUEST_TIMEOUT_SECONDS=30
```

`OPENHANDS_PUBLIC_URL` is the only origin the portal accepts for launch URLs.
The provisioner key and OpenHands session/LLM keys are never returned to the
frontend.

## Local Docker proof of concept

The repository now includes a runnable provisioner and browser gateway:

```bash
cd /Users/rahultp/Desktop/SIH/Final_Project/sih-portal
openssl rand -hex 32
# Put the generated value and the localhost settings from backend/.env.example
# into backend/.env, then:
./scripts/openhands-local.sh start
```

The helper pulls the pinned `ghcr.io/openhands/agent-canvas:1.8.0` image before
starting the provisioner. The provisioner creates a deterministic container,
state volume, and project volume for each portal user. Runtimes join the private
`sih-openhands` bridge network and publish no host ports.

For local development the portal settings are:

```bash
OPENHANDS_ENABLED=true
OPENHANDS_PROVISIONER_URL=http://localhost:8090
OPENHANDS_PROVISIONER_API_KEY=<generated 64-character hex secret>
OPENHANDS_PUBLIC_URL=http://localhost:8090
OPENHANDS_REQUEST_TIMEOUT_SECONDS=30
```

The provisioner uses the Docker socket to create runtimes. Socket access is
effectively host-administrator access, so this Compose deployment is for a
single trusted development machine only. The socket is mounted into the
provisioner control plane, never into an OpenHands user runtime.

### Local launch flow

1. The portal ensures `sih-user-<portal user id>` through the authenticated
   control API.
2. The provisioner starts or resolves that user's pinned Agent Canvas container.
3. Launch creates a 60-second, single-use random ticket bound to the user and
   workspace.
4. Redeeming the ticket sets an HttpOnly, SameSite browser session and redirects
   to `/canvas`.
5. The gateway routes HTTP and WebSocket traffic to only that session's
   container and injects the container API key upstream. Real backend keys are
   scrubbed from browser responses.

Operational commands:

```bash
./scripts/openhands-local.sh status
./scripts/openhands-local.sh logs
./scripts/openhands-local.sh restart
./scripts/openhands-local.sh stop
```

Runtime containers are recreated from the provisioner database after a restart;
named state and project volumes are retained.

## Provisioner API contract

All provisioner calls use:

```http
Authorization: Bearer <OPENHANDS_PROVISIONER_API_KEY>
Content-Type: application/json
```

### Ensure workspace

```http
POST /v1/workspaces
Idempotency-Key: openhands-user-42
```

```json
{
  "provider": "openhands",
  "workspace_key": "sih-user-42",
  "identity": {
    "user_id": "42",
    "department_id": 3,
    "department_scope": "engineering",
    "role": "user"
  }
}
```

Return `200` or `201`:

```json
{
  "workspace_id": "oh-ws-01J...",
  "status": "ready",
  "launch_url": "https://code.example.gov.in/workspaces/oh-ws-01J..."
}
```

`status` may be `provisioning` or `ready`. A provisioning response may omit
`launch_url`. The ready URL is persisted internally and therefore must not
contain credentials, query parameters, or fragments.

### Mint launch handoff

```http
POST /v1/workspaces/oh-ws-01J.../launch
```

```json
{
  "identity": {
    "user_id": "42",
    "department_id": 3,
    "department_scope": "engineering",
    "role": "user"
  }
}
```

Return a short-lived, single-use URL:

```json
{
  "launch_url": "https://code.example.gov.in/handoff?ticket=<single-use>"
}
```

The portal does not store this URL and marks its own response `Cache-Control:
no-store`. The provisioner must bind the ticket to the portal user and target
workspace, expire it quickly, redeem it once, and establish an HttpOnly Secure
session at the Agent Canvas gateway.

## Required isolation checks

- Map `workspace_key` to exactly one portal `user_id`; treat create as idempotent.
- Never choose a workspace from browser-supplied user, department, or URL data.
- Reject a launch when the ticket identity does not own the workspace.
- Keep repository credentials and LLM keys in the runtime secret store.
- Use separate worktrees/volumes and conversation state per user.
- Audit provision, launch, stop, and destroy events by portal user ID.
- Pin OpenHands Agent Canvas and Agent Server images; upgrade deliberately.

The upstream OpenHands self-hosting guide also requires TLS, a protected Agent
Server API key, and WebSocket-aware reverse proxying for remote deployments.
