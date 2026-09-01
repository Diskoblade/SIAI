# SIAI Technical Approach

## 1. Objective

SIAI is implemented as a secure, multi-user knowledge and productivity portal.
It combines private document retrieval, an agentic RAG workflow, persistent
conversations, scientific tools, presentation generation, document editing, and
isolated browser coding workspaces.

The central design rule is:

> Use the LLM for language and bounded reasoning. Use deterministic backend code
> for identity, authorization, storage, validation, and tool execution.

This prevents prompts, model output, or browser-supplied metadata from widening
a user's access to private information.

## 2. System architecture

```text
Browser (React + Vite)
        |
        | HTTPS / JSON / JWT
        v
FastAPI application
        |
        +-- Authentication and authorization services
        +-- Document ingestion and private file storage
        +-- LangGraph RAG and tool orchestration
        +-- Conversation and memory services
        +-- Approval-note and ONLYOFFICE integration
        +-- OpenHands workspace control API
        |
        +-- SQLAlchemy -> SQLite (prototype) / PostgreSQL-ready schema
        +-- Vector store -> SQLite default / Qdrant optional
        +-- LLM -> OpenAI-compatible endpoint / offline fallback
        +-- Embeddings -> hashing default / OpenAI / Ollama BGE-M3
        |
        +-- ONLYOFFICE Document Server (Docker)
        +-- OpenHands per-user runtime provisioner (Docker proof of concept)
```

The frontend is an untrusted client. User IDs, department IDs, document owners,
visibility filters, vector collection selection, callback signatures, and tool
function names are resolved or validated by the backend.

## 3. Application layers

### Frontend

The browser application uses React 18, React Router, Vite, Lucide icons, Motion,
and custom CSS. It provides:

- Authentication, signup, and account status pages.
- A persistent multi-turn conversation interface.
- Private knowledge-file upload, listing, sharing, and deletion.
- Citation, calculation, and answer-provenance displays.
- Browser-side editable PPTX generation and download.
- A protected OpenHands coding-workspace launcher and saved code editor.
- Approval-note generation and an embedded ONLYOFFICE editor.

The frontend calls the backend through the shared API client in
`frontend/src/services/api.js`. It does not query the database or vector store
directly.

### Backend

FastAPI exposes typed routes and uses Pydantic for request/response validation.
Business rules live in service modules rather than route handlers. SQLAlchemy
provides the persistence boundary, allowing the current SQLite database to be
migrated to PostgreSQL without changing route contracts.

Primary backend areas:

- `app/routes/`: HTTP endpoints and dependency wiring.
- `app/services/`: authorization, storage, conversations, IDE, and approval notes.
- `app/rag/`: ingestion, embeddings, retrieval, graph nodes, LLMs, and reranking.
- `app/agent_tools/`: bounded deterministic tools such as `fluids`.
- `app/media/`: slide charts, diagrams, analytics, and richer parsing.
- `app/models/`: SQLAlchemy entities and ownership metadata.

## 4. Identity and authorization

Passwords are hashed with Argon2id. Successful login returns a signed JWT. On
every protected request, the backend validates the token and reloads the user
from the database so disabled accounts, role changes, and department changes
take effect immediately.

For RAG, the backend creates a frozen `UserContext` containing the trusted user
ID, department ID, department scope, and resolved role. It is never constructed
from question text or arbitrary browser fields.

The document visibility rule is:

```text
(visibility == PRIVATE AND owner_user_id == current_user.id)
OR (visibility == DEPARTMENT AND department_id == current_user.department_id)
OR (visibility == COMMON)
```

The rule is enforced before similarity scoring in the SQLite vector store and as
a server-side payload filter in Qdrant. Unauthorized chunks therefore cannot
enter reranking, LangGraph state, citations, conversation memory, or the LLM
prompt.

## 5. Document ingestion

### Upload flow

```text
Authenticated upload
  -> validate extension, content, and size
  -> assign owner and PRIVATE visibility on the server
  -> parse document into structured blocks
  -> split blocks into bounded overlapping chunks
  -> generate embeddings in batches
  -> store document and chunk metadata in SQL
  -> upsert vectors into the selected vector store
  -> return indexing status and chunk count
```

Supported formats are PDF, DOCX, XLSX, CSV, Markdown, and TXT. Docling is used
when installed and enabled; otherwise pypdf, python-docx, openpyxl, and built-in
CSV/text parsers provide deterministic fallbacks.

Each chunk inherits immutable ownership and visibility metadata from its parent
document. A user can share an owned private file with their department without
re-embedding it. Deleting a file removes its SQL chunks and corresponding Qdrant
points.

## 6. Vector storage and retrieval

The vector layer is provider-based:

| Provider | Purpose | Selection |
| --- | --- | --- |
| `SqliteVectorStore` | Local prototype, scoped cosine and lexical retrieval | Default |
| `QdrantVectorStore` | Dedicated vector database with payload filtering | `VECTOR_STORE=qdrant` |

Embeddings are also provider-based:

| Provider | Purpose | Selection |
| --- | --- | --- |
| `HashingEmbedder` | Dependency-free deterministic local embedding | Default |
| `OpenAIEmbedder` | Hosted OpenAI-compatible embedding endpoint | `EMBEDDING_PROVIDER=openai` |
| `OllamaEmbedder` | Local model such as BGE-M3 | `EMBEDDING_PROVIDER=ollama` |

Retrieval combines dense cosine similarity and sparse token overlap. The two
ranked result lists are fused using Reciprocal Rank Fusion, then a reranker keeps
the most relevant authorized chunks.

## 7. Agentic RAG workflow

LangGraph implements the query workflow as explicit nodes and conditional
edges. The compiled flow is:

```text
START
  -> resolve_access_scope
  -> contextualize_query
  -> understand_query
  -> scientific_tool
       -> if calculation: deterministic answer
       -> otherwise:
          plan_query
          -> retrieval_router
          -> hybrid_retriever
          -> reranker
          -> evidence_grader
               -> if insufficient and retries remain: query_rewriter -> retrieve
               -> otherwise: context_builder
          -> grounded_answer or general_knowledge_answer
          -> claim_verifier
          -> citation_validator
  -> END
```

### Query processing

1. The backend authenticates the caller and builds `UserContext`.
2. Recent messages from an owned conversation are loaded within count and
   character limits.
3. Follow-up language is converted into a standalone retrieval question.
4. The graph detects direct tool requests and presentation intent.
5. Every retrieval attempt uses the same frozen authorization context.
6. Results are reranked and graded for evidence sufficiency.
7. A bounded rewrite loop can retry retrieval; it cannot run indefinitely.
8. The answer is generated from authorized context and citations are validated
   against the retrieved document IDs.
9. The result and provenance are persisted with the conversation and audit log.

### General-knowledge fallback

When authorized retrieval remains insufficient after the retry limit, the graph
can call the configured LLM using only the user's question. Retrieved chunks are
not supplied to this branch. Its response is labelled
`answer_source="general_knowledge"`, has no document citations, and includes a
verification warning because model knowledge can be incomplete or outdated.

With the offline extractive answerer, no model knowledge is available, so this
branch returns `answer_source="unavailable"`. It can also be disabled with
`RAG_GENERAL_KNOWLEDGE_FALLBACK_ENABLED=false`.

## 8. Persistent conversations and memory

Conversation sessions and messages are stored in SQL and scoped to an exact
owner user ID. Reopening a conversation reads the stored answer, citations,
calculation result, and presentation specification instead of rerunning old
queries.

For a new message, only bounded recent history is sent to query
contextualization. Conversation history cannot modify `UserContext` or the
vector-store filter.

A separate classifier identifies durable user decisions, notes, and preferences.
Accepted memories are stored as private vector-backed content belonging to the
same user and enter retrieval through the normal authorization boundary.

## 9. Agent tools

### Fluid-dynamics calculations

Explicit numeric fluid-dynamics questions are routed to the server-side
`fluids` tool. The LLM may select an operation and extract SI values, but it
cannot submit Python code or an arbitrary function name.

The executor uses a fixed operation allow list, validates finite bounded numeric
inputs, discards unsupported arguments, and invokes `fluids` directly. The
result includes inputs, outputs, SI units, operation name, and library version.
Calculation answers bypass document retrieval and use
`answer_source="calculation"`.

### PowerPoint generation

Presentation generation activates only for explicit slide-creation intent. The
backend creates a bounded presentation specification. Document-backed decks can
only use content represented by validated citations; general-knowledge decks
include provenance warnings and no source IDs.

The browser converts the specification into an editable `.pptx` using pinned
`@office-kit/pptx` 0.12.0 and downloads it locally. API keys and vector-store
access remain on the server. Optional DuckDB, Vega-Lite/vl-convert, and Mermaid
components provide tables, charts, and diagrams.

## 10. OpenHands coding workspaces

The portal does not expose a shared unrestricted OpenHands runtime. Its flow is:

```text
Authenticated portal user
  -> backend resolves trusted identity
  -> internal provisioner ensures one workspace for that user
  -> provisioner starts an isolated Agent Canvas container and persistent volumes
  -> backend requests a short-lived single-use launch ticket
  -> browser redeems the ticket into an HttpOnly gateway session
```

The local proof of concept uses Docker with deterministic per-user containers,
state volumes, project volumes, a private bridge network, and no runtime host
ports. Portal code projects are also stored by user in SQL so they remain
available after logout and login.

The Docker socket is mounted only into the trusted local provisioner control
plane. This arrangement is suitable for a local proof of concept; production
should use stronger pod/container isolation, network policies, quotas, TLS, and
managed secret storage.

## 11. Approval notes and ONLYOFFICE

Admins upload a DOCX letterhead and configure approval-note types. Creating a
note performs the following flow:

```text
Request parameters
  -> generate bounded note content
  -> copy the active letterhead
  -> replace supported placeholders in body/header/footer/content controls
  -> otherwise insert content after the letterhead layout
  -> store the private generated DOCX
  -> open a server-signed ONLYOFFICE editor session
```

The master letterhead is never edited. ONLYOFFICE fetches the generated copy
through a token-bound backend URL. Auto-save or explicit force-save calls the
JWT-validated backend callback, which downloads the edited DOCX, atomically
stores a new file version, and updates database metadata. Back and Download
request a save before leaving the editor.

## 12. Persistence model

The prototype uses SQLite through SQLAlchemy for:

- Users, roles, departments, and account status.
- Documents, chunks, ownership, and visibility.
- RAG audit records.
- Conversations and messages.
- Private vector-backed memories.
- OpenHands workspace metadata and saved code projects.
- Approval-note templates, types, generated documents, and versions.

Uploaded files, DOCX templates, and approval-note versions are stored under the
private backend storage directory rather than a public frontend path. The ORM
schema and configuration allow migration to PostgreSQL for production.

## 13. Security controls

- Ownership and department scope are resolved from authenticated database data.
- Normal uploads default to private ownership.
- Authorization is enforced inside retrieval, not after results are returned.
- Admin role does not automatically expose another user's private knowledge.
- Request schemas reject unknown ownership and scope fields.
- Tool execution uses fixed operations and validated inputs.
- LLM output cannot select arbitrary server functions or database filters.
- ONLYOFFICE configuration and callbacks use server-side JWT signing.
- OpenHands launch URLs are origin-checked and use short-lived single-use tickets.
- Secrets remain in backend or provisioner environment variables.
- Retrieval retries, conversation history, context size, file size, and tool
  inputs are bounded.

## 14. Configuration strategy

Heavy services are behind provider interfaces so the project runs locally with
minimal dependencies while retaining production upgrade paths.

```text
LLM_PROVIDER=extractive|openai
EMBEDDING_PROVIDER=hashing|openai|ollama
VECTOR_STORE=sqlite|qdrant
RERANKER_PROVIDER=lexical|bge
OPENHANDS_ENABLED=true|false
ONLYOFFICE_ENABLED=true|false
FLUIDS_TOOL_ENABLED=true|false
```

In the checked local environment, the reasoning/answer provider is
OpenAI-compatible, OpenHands and ONLYOFFICE are enabled, and unspecified RAG
providers use hashing embeddings, SQLite vector storage, and lexical reranking.

## 15. Verification approach

The repository includes focused tests for:

- Authentication, JWT behavior, signup, and login.
- Private/department/common retrieval isolation.
- Malicious planner and query-rewriter attempts to access private data.
- Upload parsing, vector indexing, sharing, and deletion.
- Qdrant payload filters and SQLite retrieval.
- Multi-turn conversations and private memory.
- General-knowledge fallback provenance.
- Fluid-dynamics operation validation.
- Presentation intent and PPTX specifications.
- OpenHands workspace ownership and provisioning.
- ONLYOFFICE editor configuration, callback authentication, DOCX versioning,
  force-save, and letterhead population.

Frontend changes are verified with the Vite production build and browser-level
checks for critical workflows. Backend changes are verified with pytest and
service-level tests that mock external providers where appropriate.

## 16. Production evolution

The current architecture supports incremental production hardening:

1. Move application metadata from SQLite to PostgreSQL.
2. Enable Qdrant with indexed owner, department, and visibility payload fields.
3. Use production embeddings and reranking, then re-ingest existing documents.
4. Replace local file storage with private object storage and retention policies.
5. Put the API, ONLYOFFICE, and OpenHands gateway behind TLS and an authenticated
   reverse proxy.
6. Replace Docker-socket provisioning with Kubernetes pods and per-user PVCs.
7. Move browser JWTs to Secure, HttpOnly cookies with CSRF protection.
8. Add centralized audit reporting, monitoring, backups, and key rotation.

## 17. Related documentation

- [RAG architecture](RAG_ARCHITECTURE.md)
- [Technology and source references](SOURCES.md)
- [OpenHands integration](OPENHANDS_INTEGRATION.md)
- [ONLYOFFICE approval notes](ONLYOFFICE_APPROVAL_NOTES.md)
- [Project setup and API overview](../README.md)
