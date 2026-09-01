# ONLYOFFICE Approval Notes

Create, edit (in an embedded **ONLYOFFICE Docs Community Edition** editor), store,
and download **Approval Note** DOCX documents built from a company letterhead.

## Architecture

```
Browser (React) ── JWT ──▶ FastAPI backend ──▶ SQLite (metadata)
                                    │
                                    ├─▶ Private file storage (backend/storage/)
                                    │      templates/  approval_notes/
                                    │
                                    └─▶ Local LLM / RAG (content generation)

ONLYOFFICE Document Server (Docker) ──fetch DOCX──▶ backend /api/onlyoffice/documents/:id/file
                                    ◀──save callback── backend /api/onlyoffice/callback/:id
   (reaches the host backend via host.docker.internal; JWT-secured both ways)
```

- The **master letterhead is never edited**. Each Approval Note is a private copy
  with placeholders replaced (or a graceful fallback insertion).
- The ONLYOFFICE editor config (incl. its JWT) is **signed server-side**; the
  browser never signs anything.
- Access control is by the existing **department + role** model, single-tenant
  (`company_id` defaults to `1`) and always derived from the authenticated user.

## Prerequisites

- Docker (for the ONLYOFFICE Document Server), the existing Python venv, Node.
- `python-docx` (already in requirements) for DOCX manipulation — no Word/LibreOffice.

## 1. Environment variables

`backend/.env` (see `backend/.env.example`):

```
ONLYOFFICE_ENABLED=true
ONLYOFFICE_URL=http://localhost:8085
APP_BASE_URL_FOR_ONLYOFFICE=http://host.docker.internal:8010
ONLYOFFICE_JWT_SECRET=<python -c "import secrets;print(secrets.token_urlsafe(48))">
DOCUMENT_STORAGE_DIR=storage
```

Root `.env` for docker-compose (see `.env.example`) — **must match** the backend:

```
ONLYOFFICE_JWT_SECRET=<same value as backend/.env>
```

Never commit real secrets.

## 2. Start ONLYOFFICE

```bash
# from the project root
docker compose up -d
# wait ~30s, then:
curl -s http://localhost:8085/healthcheck   # -> true
```

The Admin → Approval Settings page shows **ONLYOFFICE: Connected** when reachable.

## 3. Start the app (unchanged)

```bash
cd backend && ./.venv/bin/python -m uvicorn app.main:app --port 8010
cd frontend && npm run dev        # http://localhost:5173
```

## 4. Admin: letterhead + types

- **Admin → Approval Settings** (`/admin/approval-notes`):
  - Upload/replace the `.docx` **letterhead** (only DOCX; size-validated; stored
    privately; the previous version is retired, not deleted).
  - Manage **Approval Note types** (the 9 defaults are seeded; add/activate/deactivate).
- **Template placeholders** (optional, in the letterhead body/header/footer):
  `{{APPROVAL_NOTE_TITLE}}`, `{{APPROVAL_NOTE_CONTENT}}`, `{{APPROVAL_NOTE_NUMBER}}`,
  `{{DATE}}`, `{{DEPARTMENT}}`, `{{PREPARED_BY}}`, `{{COMPANY_NAME}}`.
  If no placeholders are present, the title + content are inserted at the top of
  the body (logos/headers/footers/tables/margins are preserved).

## 5. User: create + edit

**Approval Notes** (`/approval-notes`): pick a type, add parameters → the local
LLM drafts the content → the letterhead is copied and populated → you're taken to
the embedded **ONLYOFFICE editor**. Edits auto-save via the callback. Download the
DOCX any time.

## 6. Document callback behavior

`POST /api/onlyoffice/callback/:noteId?token=…`

- Validated by (a) our short-lived signed access token (bound to that note) and
  (b) the ONLYOFFICE JWT on the callback body.
- Status **2/6** (save / force-save): the backend fetches the new file from the
  Document Server, writes it **atomically to a new key**, bumps `document_version`
  (which changes the ONLYOFFICE `key`), and only then removes the old file.
- Always responds `{ "error": 0 }` to acknowledge; failures are logged and never
  destroy the current version.

## API surface

| Method | Path | Who |
| --- | --- | --- |
| POST | `/api/admin/approval-notes/letterhead` | admin |
| GET | `/api/admin/approval-notes/letterhead` · `/download` | admin |
| GET/POST/PATCH | `/api/admin/approval-notes/types[/{id}]` | admin |
| GET | `/api/approval-notes/types` | user (active only) |
| POST/GET | `/api/approval-notes` · `/{id}` | user (scoped) |
| GET | `/api/approval-notes/{id}/download` | user (scoped) |
| GET | `/api/approval-notes/{id}/editor-config` | user (server-signed) |
| GET | `/api/onlyoffice/documents/{id}/file` | Document Server (token) |
| POST | `/api/onlyoffice/callback/{id}` | Document Server (token + JWT) |
| GET | `/api/integrations/onlyoffice/health` | any authenticated |

## Troubleshooting

- **Editor won't load** → is the container up (`docker compose ps`)? Is
  `ONLYOFFICE_URL` reachable from the browser?
- **Saves don't persist** → the Document Server must reach the backend at
  `APP_BASE_URL_FOR_ONLYOFFICE`. On Docker Desktop use `host.docker.internal`; on
  Linux the compose `extra_hosts` maps it. The callback file URL is rewritten to
  `ONLYOFFICE_URL`'s origin so the backend can fetch the cached file.
- **401 on callback** → `ONLYOFFICE_JWT_SECRET` must be identical in
  `backend/.env` and the compose `.env`.
- **415 on upload** → only `.docx` is accepted.
- **409 on create** → no active letterhead configured yet.

## Production considerations

- Terminate TLS in front of both the app and the Document Server; use real
  hostnames instead of `host.docker.internal`.
- Put `backend/storage/` on a private, backed-up volume (never web-served).
- Keep JWT enabled; rotate `ONLYOFFICE_JWT_SECRET`.
- Consider retaining historical document versions (today the latest saved DOCX is
  kept and the version number is recorded).
```
