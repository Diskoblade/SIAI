# Sovereign Knowledge Portal

**Secure AI-powered private and departmental knowledge access** — an internal
AI/RAG platform that gives each user a private knowledge space and supports
explicit, reversible sharing with their department.

```
Signup → User DB → JWT Auth → Trusted user context
       → Private + department + common vector filter → RAG/LLM
```

The central security property:

> Authentication identifies the user; **backend-side authorization** determines
> ownership and visibility before retrieval. The frontend never controls owner
> IDs, department IDs, or vector filters.

**Build status**
- ✅ **Auth subsystem** — signup/login/JWT/admin approval/department + role.
- ✅ **RAG Milestone 1** — scope resolver, document models & ingestion,
  mandatory scope-filtered hybrid retrieval, citations, audit log, isolation
  tests (incl. prompt injection).
- ✅ **RAG Milestone 2** — **LangGraph** agentic graph (query understanding →
  planner → router → retriever → reranker → evidence grader → query rewriter →
  context builder → answer → claim verifier → citation validator), reranker,
  and a **hosted OpenAI/ChatGPT** provider (plus Ollama/Qdrant) — all pluggable.
- ✅ **Document uploads** — PDF, DOCX, XLSX, CSV, Markdown, and TXT parsing,
  chunking, embedding, vector indexing, scoped document listing, and upload UI.
- ✅ **Private knowledge spaces** — every normal upload defaults to `PRIVATE`;
  owners can reversibly share with their department without re-embedding.
- ✅ **Conversation memory** — decisions, notes, and preferences are classified,
  stored privately, and retrieved through the same authorized vector layer.
- ✅ **Multi-turn conversations** — owner-isolated sessions persist complete
  message history and supply bounded recent context for follow-up questions.
- ✅ **Answer fallback** — exhausted retrieval can use clearly labelled general
  model knowledge without document citations or access to unauthorized chunks.
- ✅ **PowerPoint generation** — slide-intent routing and editable `.pptx`
  downloads generated with the pinned `@office-kit/pptx` browser library.
- ✅ **Scientific calculations** — explicit fluid-dynamics requests activate a
  bounded server-side `fluids` 1.3.1 tool with validated SI inputs and outputs.
- ✅ **OpenHands integration** — protected Coding Workspace page plus a runnable
  local Docker provisioner/gateway with one persistent Agent Canvas runtime per user.
- ⏳ **Next** — metadata/SQL retrieval and stronger answer verification. See the roadmap.

Full design, provider setup (**ChatGPT/OpenAI** included), and roadmap:
[`docs/RAG_ARCHITECTURE.md`](docs/RAG_ARCHITECTURE.md).
OpenHands deployment and provisioner contract:
[`docs/OPENHANDS_INTEGRATION.md`](docs/OPENHANDS_INTEGRATION.md).
Upstream projects, official documentation, and RAG research references:
[`docs/SOURCES.md`](docs/SOURCES.md).
End-to-end implementation and engineering approach:
[`docs/TECHNICAL_APPROACH.md`](docs/TECHNICAL_APPROACH.md).

---

## Stack

| Layer     | Choice                                                                 |
| --------- | --------------------------------------------------------------------- |
| Frontend  | React 18 + Vite, `@office-kit/pptx` 0.12.0, custom CSS              |
| Backend   | FastAPI + SQLAlchemy 2.0 ORM + Pydantic v2 + `fluids` 1.3.1           |
| Database  | SQLite (prototype) — ORM-structured for an easy PostgreSQL migration |
| Passwords | **Argon2id** via `argon2-cffi` (never plaintext)                     |
| Tokens    | **JWT (HS256)** via `PyJWT`, secret from env                         |

### Notable decisions
- **Argon2id over passlib/bcrypt**: `passlib` depends on Python's `crypt`
  module, which was removed in Python 3.13+. `argon2-cffi` is clean, modern,
  and the strongest option.
- **PyJWT over python-jose**: the actively-maintained equivalent the brief
  permits; identical HS256 tokens.
- **Token storage = `localStorage` + `Authorization` header** (prototype).
  This is simpler than HttpOnly cookies but **more exposed to XSS**. For
  production, move the JWT into an HttpOnly, Secure cookie and add CSRF
  protection. No passwords are ever stored in the browser.

---

## Project layout

```
sih-portal/
├── compose.openhands.yml               # local OpenHands control plane
├── provisioner/                        # Docker lifecycle + launch gateway
├── scripts/openhands-local.sh          # start/stop/status helper
├── backend/
│   ├── app/
│   │   ├── main.py                     # app wiring, CORS, startup seeding
│   │   ├── database.py                 # engine/session (SQLite→PG ready)
│   │   ├── seed.py                     # idempotent department seeding
│   │   ├── models/                     # User, Department (+ enums)
│   │   ├── schemas/                    # Pydantic request/response models
│   │   ├── routes/                     # auth, departments, admin, rag
│   │   ├── services/                   # auth, authorization, rag, serializers
│   │   └── core/                       # config, security, dependencies
│   ├── tests/                          # 28 tests (signup/login/jwt/authz)
│   ├── create_admin.py                 # CLI to create the first admin
│   ├── requirements.txt
│   └── .env.example
└── frontend/
    ├── src/
    │   ├── pages/                       # Login, Signup, Dashboard, Admin
    │   ├── components/                  # ProtectedRoute, AdminRoute, Navbar…
    │   ├── context/AuthContext.jsx      # login/logout/getCurrentUser/isAuth
    │   └── services/                    # api.js, auth.js
    ├── package.json
    └── .env.example
```

---

## Backend setup

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create your env file and generate a strong JWT secret:

```bash
cp .env.example .env
python -c "import secrets; print('JWT_SECRET_KEY=' + secrets.token_urlsafe(48))"
# paste the printed line into .env, replacing the placeholder
```

Initialize the database and seed the five departments
(Finance, HR, Legal, Engineering, Administration):

```bash
python -m app.seed
```

Create the first administrator (prompts for a hidden password — nothing is
hard-coded):

```bash
python create_admin.py
# or non-interactively:
python create_admin.py --name "Portal Admin" --email admin@example.com --department Administration
```

Run the API (auto-creates tables + seeds departments on startup):

```bash
uvicorn app.main:app --reload --port 8000
```

Interactive API docs: <http://localhost:8000/docs>

> **Port note:** if `:8000` is already in use, run e.g. `--port 8010` and set
> the frontend's `VITE_API_URL` (below) to match.

Run the tests:

```bash
pytest
```

---

## Frontend setup

```bash
cd frontend
npm install
cp .env.example .env      # empty VITE_API_URL uses the local /api proxy
npm run dev
```

Open <http://localhost:5173>.

During local development Vite proxies `/api` to `127.0.0.1:8010`. Set an
absolute `VITE_API_URL` only when frontend and backend are deployed on separate
origins. Backend CORS remains restricted to `FRONTEND_URL`, never a wildcard.

---

## Local OpenHands workspaces

Docker Desktop must be running. Generate a provisioner key and add the four
`OPENHANDS_*` values shown in `backend/.env.example` to `backend/.env`. Then run:

```bash
./scripts/openhands-local.sh start
```

The first start pulls the pinned Agent Canvas image and can take several
minutes. The provisioner is exposed at <http://localhost:8090>; individual
OpenHands containers have no host ports. Sign in to the portal, open `/code`,
and select **Start coding**. Each portal user receives separate state and
project volumes.

```bash
./scripts/openhands-local.sh status
./scripts/openhands-local.sh logs
./scripts/openhands-local.sh stop
```

Stopping removes runtime containers so the Docker network can shut down, but
keeps their named volumes and the provisioner database. Starting again restores
the same user workspaces.

---

## Demo walk-through

1. **Sign up** at `/signup` — pick a department, submit. The account is created
   `pending`; you are told it awaits administrator approval. No token is issued.
2. **Try to log in** as that user → blocked with *"awaiting administrator
   approval."*
3. **Log in as the admin**, open **Admin**, find the pending user, optionally
   change their department, and click **Approve**.
4. **Log in as the user** → Dashboard shows their name, department, and role.
5. Open **Documents**, upload a supported file, and wait for indexing. Normal
   user uploads are private automatically.
6. Ask a question in the **Departmental Knowledge Assistant**. The response
   shows the **server-derived** collection (e.g. `dept_engineering`) — the
   client never sends a collection name.
7. In **My files**, enable sharing for a selected file. Users in the same
   department can retrieve it immediately; disabling sharing makes it private
   again without regenerating embeddings.
8. Ask `Create a 5-slide presentation about ...` to receive an editable
   PowerPoint download. The deck identifies whether it uses departmental
   documents or general model knowledge.
9. Ask `Calculate Reynolds number for velocity 2 m/s, diameter 0.05 m, density
   998 kg/m3, and dynamic viscosity 0.001 Pa*s.` The assistant executes the
   `fluids` tool and displays the structured result and library version.
10. Continue in the same conversation with a follow-up such as `Can you compare
    that with next year?`, or create another private session from the sidebar.

### Local development credentials
Created only for local testing (see `create_admin.py` above):

| Role  | Email               | Password       |
| ----- | ------------------- | -------------- |
| Admin | `admin@example.com` | `AdminPass123` |

> Note: `email-validator` rejects reserved domains like `.local`, so use a
> normal domain (`example.com`, a real `.gov.in`, etc.) for accounts.

---

## API endpoints

| Method | Path                        | Auth        | Purpose                               |
| ------ | --------------------------- | ----------- | ------------------------------------- |
| POST   | `/api/auth/signup`          | public      | Create a `pending` account            |
| POST   | `/api/auth/login`           | public      | Verify credentials/status → JWT       |
| GET    | `/api/auth/me`              | bearer      | Current user's safe profile           |
| POST   | `/api/auth/logout`          | bearer      | Stateless logout                      |
| GET    | `/api/departments`          | public      | Department list for the signup form   |
| GET    | `/api/admin/users`          | **admin**   | List users (optional `?status=`)      |
| PATCH  | `/api/admin/users/{id}`     | **admin**   | Change status / department / role     |
| GET    | `/api/documents`            | bearer      | List owned files (`?view=shared` for shared/common) |
| POST   | `/api/documents`            | bearer      | Upload + ingest a file (private by default) |
| POST   | `/api/documents/text`       | bearer      | Ingest raw text                       |
| PATCH  | `/api/documents/{id}/visibility` | owner | Share/unshare without re-embedding |
| DELETE | `/api/documents/{id}`       | owner       | Delete an owned file and its vectors  |
| GET    | `/api/memories`             | bearer      | List the caller's private memories    |
| POST   | `/api/memories`             | bearer      | Save a private memory                 |
| DELETE | `/api/memories/{id}`        | owner       | Delete a private memory               |
| GET    | `/api/conversations`        | bearer      | List the caller's private sessions    |
| POST   | `/api/conversations`        | bearer      | Create a private conversation         |
| GET    | `/api/conversations/{id}/messages` | owner | Reload persisted session messages |
| DELETE | `/api/conversations/{id}`   | owner       | Delete a session and its messages     |
| POST   | `/api/rag/query`            | bearer      | Ask a question — authorized retrieval + citations |
| GET    | `/api/rag/history`          | bearer      | The caller's own recent queries       |
| GET    | `/api/rag/status`           | bearer      | Active providers (ChatGPT vs offline) |
| GET    | `/api/ide/status`           | bearer      | Current user's OpenHands workspace state |
| POST   | `/api/ide/workspaces`       | bearer      | Ensure the caller's isolated workspace |
| POST   | `/api/ide/workspaces/launch`| bearer      | Mint a one-time launch handoff |
| GET    | `/api/health`               | public      | Health check                          |

**Frontend pages:** `/login`, `/signup`, `/dashboard` (multi-session conversation window),
`/documents` (upload + scoped list), `/recent` (query history), `/code`
(OpenHands coding workspace), `/admin`.

### RAG quickstart (after the backend is running)

```bash
# seed a few cross-department sample documents (finance/hr/legal/eng/common/shared)
python -m app.seed_documents
```

`POST /api/rag/query` accepts `{"question": "...", "conversation_id": "..."}`;
`conversation_id` is optional for backward-compatible one-off requests and is
always checked against the authenticated owner.
It returns `{answer, answer_source, citations[], evidence_status,
documents_used[], authorized_collection, presentation?, calculation?,
conversation_id?, conversation_title?}`.
`answer_source` is `documents`, `general_knowledge`, `calculation`, or
`unavailable`. It never accepts a
`department` or `collection_name` —
scope is derived from the authenticated user. Full design + provider config +
roadmap: [`docs/RAG_ARCHITECTURE.md`](docs/RAG_ARCHITECTURE.md).

---

## How authentication works
1. Login verifies the email + Argon2id password hash and the account `status`.
2. Only `approved` accounts receive a **JWT** (`sub`, `department_id`, `role`,
   `iat`, `exp`) signed with `JWT_SECRET_KEY`.
3. Protected routes use one dependency, `get_current_user`, which:
   decodes/verifies the token → checks expiry → loads the user **from the DB**
   → confirms the account is still `approved`. Authorization data is read from
   the database, **not** the token, so a disabled account's old JWT stops
   working immediately.

## How department authorization works
- `services/authorization_service.get_authorized_vector_collection()` reads the
  authenticated user's `department_id`, loads the department, and returns its
  `vector_collection`. This is the **only** way a collection is chosen.
- `/api/rag/query` accepts **only** a `question` (extra fields are rejected).
  A user cannot reach another department's data via the request body, query
  string, headers, or localStorage.

---

## Vector storage
The default `VECTOR_STORE=sqlite` keeps embedded chunks in the application
database and performs scoped cosine + lexical retrieval locally. Set
`VECTOR_STORE=qdrant` for a dedicated vector database; the first upload creates
the configured Qdrant collection automatically. Both providers enforce the
same metadata rule before scoring: own `PRIVATE`, same-department `DEPARTMENT`,
or `COMMON`. Admin status does not bypass private ownership.

Existing databases are upgraded non-destructively at startup because this
prototype does not yet use Alembic. New nullable metadata columns are added and
legacy `created_by` values are backfilled into `owner_user_id`; existing scope
rows retain their prior behavior until an owner explicitly changes visibility.

## Migrating SQLite → PostgreSQL
Change `DATABASE_URL` in `backend/.env` to a `postgresql+psycopg://…` URL. The
engine drops the SQLite-only `check_same_thread` automatically. For real
migrations, add Alembic; the model definitions do not change.
