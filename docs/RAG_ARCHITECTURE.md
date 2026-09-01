# Agentic RAG Platform — Architecture & Roadmap

This document covers the owner-first RAG platform layered on top of the existing
authentication subsystem. **Authentication was not rebuilt** — the RAG
layer consumes the trusted user/department/role state it already produces.

## Security-first principle

> Use agents for reasoning. Use **deterministic code** for security.

Private ownership and department isolation have higher priority than retrieval
quality or agent autonomy. Unauthorized chunks never enter the agent state or
the model context.

```
Authenticated user
   → build frozen UserContext      (user id + department id, from DB)
   → apply visibility filter       (deterministic, in the vector store)
   → retrieve authorized chunks    (only these exist downstream)
   → rerank / build context        (only authorized evidence)
   → sufficient evidence → grounded LLM answer + validated citations
   → insufficient evidence after retries → labelled general-knowledge answer
```

The fallback branch receives only the user's question. It does not receive
retrieved chunks, cannot cite departmental documents, and returns
`answer_source="general_knowledge"`. This keeps the authorization boundary
intact while avoiding an evidence-only dead end. Because model knowledge may be
wrong or outdated, the API and UI always label it and advise verification.

The authoritative visibility predicate is:

```text
(visibility == PRIVATE AND owner_user_id == current_user.id)
OR (visibility == DEPARTMENT AND department_id == current_user.department_id)
OR (visibility == COMMON)
```

This predicate is applied by `SqliteVectorStore` before local scoring and by a
Qdrant payload filter before points are returned. Admin role is deliberately
absent from the predicate, so administrators cannot retrieve another user's
private files or memories through normal APIs.

## Auth ↔ RAG integration mapping (documented mismatches)

The RAG spec assumes a slightly different shape than the existing auth models.
Nothing was broken; these are the bridges (all in
`app/services/authorization_service.py`):

| RAG spec expects | Existing auth has | Bridge |
| --- | --- | --- |
| `department_id: "finance"` (string scope) | `department_id: int`, `name`, `vector_collection` | `department_scope(dept) = slug(dept.name)` |
| private + department + common visibility | one department per user | `can_access_content(context, metadata)` |
| roles `ADMIN/DEPARTMENT_ADMIN/OFFICER/VIEWER` | roles `admin/manager/user` | `resolve_capability`: admin→ADMIN, manager→DEPARTMENT_ADMIN, user→OFFICER |
| owner/department/visibility payload filter | none | `Document`/`DocumentChunk` metadata + mandatory vector filter |
| trusted `{user_id, department_id, role}` | JWT + DB user | `build_user_context(db, user)` → frozen `UserContext` |

`UserContext` is built fresh from the DB on every request, so a disabled or
reassigned account takes effect immediately (stale JWTs cannot widen scope).

## Pluggable providers (why the defaults are local)

Every heavy component is behind an interface with a **dependency-free local
default**, so the system runs and is testable with no downloads, and real
services drop in by flipping an env var. This is exactly the modularity the spec
requires (embeddings #6, LLM #18, deterministic-vs-agentic #28).

| Component | Default (offline) | Hosted / local options | Env |
| --- | --- | --- | --- |
| Embeddings | `HashingEmbedder` | `OpenAIEmbedder` (hosted) · `OllamaEmbedder` (bge-m3) | `EMBEDDING_PROVIDER=openai\|ollama` |
| Vector store | `SqliteVectorStore` | `QdrantVectorStore` | `VECTOR_STORE=qdrant` |
| Reranker | `LexicalReranker` | `BGEReranker` (local cross-encoder) | `RERANKER_PROVIDER=bge` |
| Answer + reasoning LLM | `ExtractiveAnswerer` + heuristic nodes | OpenAI/ChatGPT · Azure · Ollama `/v1` · vLLM | `LLM_PROVIDER=openai` |

> The **security path is identical** across providers — the visibility filter is
> enforced in `SqliteVectorStore` (pre-scoring predicate) and in
> `QdrantVectorStore` (server-side payload filter). Swapping providers changes
> retrieval *quality*, never the *authorization boundary*.

### Option 1 — Hosted (ChatGPT / OpenAI), no local models

Best when local resources are limited. Put your key in `backend/.env`:

```bash
# Answer + all agentic reasoning nodes run on ChatGPT
LLM_PROVIDER=openai
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=sk-...your-key...
LLM_MODEL=gpt-4o-mini
RAG_GENERAL_KNOWLEDGE_FALLBACK_ENABLED=true

# (Optional) hosted embeddings too — otherwise the offline hashing embedder is used
EMBEDDING_PROVIDER=openai
EMBEDDING_BASE_URL=https://api.openai.com/v1
EMBEDDING_API_KEY=sk-...your-key...
EMBEDDING_MODEL=text-embedding-3-small
```

With `LLM_PROVIDER=openai`, the agentic nodes (query understanding, planning,
evidence grading, query rewriting, claim verification) use the model for
reasoning. The security nodes stay deterministic regardless.

Set `RAG_GENERAL_KNOWLEDGE_FALLBACK_ENABLED=false` for deployments that require
strictly document-grounded answers. With the offline `ExtractiveAnswerer`, no
general model knowledge exists, so an exhausted retrieval returns
`answer_source="unavailable"` instead of pretending to know the answer.

### Option 2 — Fully local (Ollama + Qdrant)

```bash
docker run -p 6333:6333 qdrant/qdrant
ollama pull bge-m3 && ollama pull llama3.1
```
```bash
EMBEDDING_PROVIDER=ollama
VECTOR_STORE=qdrant
LLM_PROVIDER=openai
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL=llama3.1
```

Re-ingest documents after switching embeddings (vectors are model-specific).
The API key is always read from the environment — never hard-coded.

## Data model

- **Document**: `id, title, owner_user_id, owner_department_id, visibility,
  shared_at, document_type, memory_category, source_filename, status,
  created_by, timestamps`.
- **DocumentChunk**: inherits `owner_user_id, department_id, visibility,
  document_type, memory_category`, plus `document_title, page, section,
  subsection, text, embedding[], tokens[]`.
- **RagAuditLog**: `user_id, department_scope, allowed_scopes[], question,
  retrieval_strategy, document_ids_accessed[], retry_count, response_status`.
  No passwords, JWTs, or secrets are logged.

`access_scope` remains only for compatibility with pre-feature rows. Every new
file and memory uses explicit owner, department, and visibility metadata.

## Upload authorization

`app/services/document_service.py` assigns every normal user or manager upload
to the authenticated user with `PRIVATE` visibility. User-supplied owner IDs,
department IDs, and scope lists are rejected. Admins retain an explicit
publishing path for one department or common organizational knowledge.

The multipart upload path accepts PDF, DOCX, XLSX, CSV, Markdown, and TXT files
up to 20 MB. Files are parsed, split into bounded overlapping chunks, embedded
in batches, persisted with inherited authorization metadata, and upserted into
the configured vector store. Empty, unreadable, encrypted, and unsupported
files are rejected instead of being marked as ingested. The upload response
includes the final indexing status and chunk count.

Only the owner can switch a file between `PRIVATE` and `DEPARTMENT`. Ownership
and department remain unchanged. The service updates the SQL chunk metadata and
Qdrant payloads in place, so sharing never regenerates embeddings.

Owners can permanently delete their files through `DELETE /api/documents/{id}`.
Deletion removes the parent document, all SQL chunks, and all matching Qdrant
points. It applies the same owner check to private and department-shared files;
being an administrator or a department peer does not permit deleting another
user's file. Conversation memories remain isolated behind their own owner-only
memory deletion API.

## Private conversation memory

`app/memory/classifier.py` keeps explicit project decisions, user notes, and
preferences while ignoring greetings, acknowledgements, recall questions, and
transient errors. `app/memory/service.py` stores accepted memories as private
vector-backed content owned by the authenticated user. The document browser
does not expose these internal memory records; `/api/memories` is owner-only.

Files, memories, department content, and common content share one retrieval
call and are merged before reranking. Because authorization happens inside the
vector store, private memory belonging to another user cannot become a
candidate, citation, or model input.

## Multi-turn conversation sessions

`Conversation` and `ConversationMessage` persist owner-isolated chat sessions.
Each assistant message stores its answer provenance, citations, document IDs,
calculation result, and presentation specification so reopening a session never
reruns an old query. `/api/conversations` list/create/delete operations and
message reads all require an exact authenticated `user_id` match; administrators
cannot open or continue another user's conversation.

`POST /api/rag/query` accepts an optional `conversation_id`. Before LangGraph
runs, the backend verifies ownership and loads at most the 12 newest messages
within a 12,000-character cap. The `contextualize_query` node converts follow-up
language into a standalone retrieval query. With a reasoning LLM it performs a
bounded rewrite; offline it deterministically joins short or pronoun-based
follow-ups with the previous user question. This context can improve retrieval
but cannot alter the frozen `UserContext` or vector authorization filter.

## Agentic graph (Milestone 2 — LangGraph)

`app/rag/graph.py` compiles the LangGraph in `app/rag/nodes.py`:

```
START → resolve_access_scope → contextualize_query → understand_query → scientific_tool
     → direct calculation → deterministic answer
     → otherwise plan_query → retrieval_router → hybrid_retriever → reranker → evidence_grader
     → (insufficient & retries left) → query_rewriter → hybrid_retriever
     → context_builder
     → sufficient evidence → grounded answer → claim verifier
     → retries exhausted → general-knowledge answer (question only)
     → citation_validator → END
```

- **Reasoning nodes** (understand/plan/grade/rewrite/verify) call the configured
  LLM; with the offline default they use deterministic heuristics, so the graph
  runs with no LLM at all.
- **Security nodes are always deterministic**: the graph carries the frozen,
  DB-resolved `UserContext`; `hybrid_retriever` passes that object to the store
  on *every* call (including after a rewrite), so ownership and department
  filters cannot be widened by planning or rewriting; `citation_validator`
  only keeps IDs present in the supplied evidence — no fabricated titles/pages.
- The rewrite loop is **retry-capped** (`MAX_RETRIEVAL_RETRIES`, default 2) so it
  can never run unbounded.
- General-knowledge answers never pass through document claim verification and
  deterministically return an empty citation list. The model is also instructed
  not to infer confidential organizational facts.

## Scientific calculation tool

Explicit numeric fluid-dynamics requests are routed by the `scientific_tool`
LangGraph node to `app/agent_tools/fluids_tool.py`. The implementation uses the
open-source [`fluids` library](https://github.com/CalebBell/fluids), pinned to
version 1.3.1. Supported operations are Reynolds number, Darcy friction factor,
straight-pipe pressure drop, minor-loss pressure drop, Froude number, Mach
number, Weber number, and cavitation number.

The LLM may select an operation, extract values, and convert them to SI units,
but it cannot provide a Python function name or expression. The executor checks
the operation against a fixed allow list, discards unknown arguments, requires
finite bounded numeric inputs, and directly calls the corresponding library
function. Direct calculations bypass retrieval and return
`answer_source="calculation"`, no document citations, a deterministic answer,
and a structured `calculation` object containing inputs, outputs, tool name, and
library version. Incomplete requests return the exact missing inputs instead of
inventing values. Set `FLUIDS_TOOL_ENABLED=false` to disable this branch.

## PowerPoint generation

Slide creation is activated server-side only when a query combines presentation
language with creation intent, such as `Create a 5-slide presentation about ...`.
The backend returns a bounded presentation specification; the browser converts
it to an editable `.pptx` with the pinned `@office-kit/pptx` 0.12.0 package.

For document-backed answers, only evidence referenced by validated citations
can enter the deck. For fallback answers, the deck has no source IDs, uses
`source_mode="general_knowledge"`, and includes a provenance warning slide. The
file is generated in the browser and downloaded directly; API keys and raw
vector-store access remain server-side.

Hybrid retrieval = dense cosine + sparse token overlap fused with Reciprocal
Rank Fusion; the reranker then reorders by query-term relevance and keeps the
top-k. `app/rag/pipeline.py` retains a non-graph deterministic path used by the
lower-level helpers and tests.

A dedicated test (`tests/test_private_knowledge.py`) drives the nodes with a
malicious planner/rewriter that targets another user's private text and confirms
the private chunk never enters retrieval results or citations.

## Roadmap (subsequent milestones)

| Phase | Work | Status |
| --- | --- | --- |
| 1 | Owner/department visibility resolver, ingestion metadata, mandatory filtering, isolation tests | ✅ done |
| 2 | **LangGraph** agentic graph (understand → plan → route → retrieve → rerank → grade → rewrite → context → answer → verify → validate), reranker, hosted **OpenAI/ChatGPT** + Ollama/Qdrant providers wired | ✅ done |
| 3 | Real BGE-M3 embeddings + Qdrant payload filtering in live use | 🔜 flip env / `docker compose` |
| 4 | Private upload UI, reversible department sharing, conversation memory, regression coverage | ✅ done |
| 5 | Richer answer formatting, metadata/SQL retrieval, stronger claim verification, audit dashboard | ⏳ |
| 6 | GraphRAG, multimodal ingestion | later |

The LangGraph state carries the frozen `UserContext` for the entire graph;
every retrieval node calls the same authorized store, and no reasoning node can
widen the owner or department filter.
