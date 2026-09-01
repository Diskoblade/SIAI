# SIAI Technology and RAG Sources

This index lists the primary upstream projects, official documentation, and
research references used by the portal. It covers direct integrations and
configurable providers; it does not list every transitive package installed by
npm or pip.

## Repository documentation

- [RAG architecture](RAG_ARCHITECTURE.md) - authorization, ingestion,
  retrieval, agent graph, fallback behavior, conversations, calculations, and
  presentation generation.
- [OpenHands integration](OPENHANDS_INTEGRATION.md) - per-user runtime and
  provisioner contract.
- [ONLYOFFICE approval notes](ONLYOFFICE_APPROVAL_NOTES.md) - letterhead,
  embedded editor, save callback, and private DOCX storage.
- [Project README](../README.md) - setup, API routes, stack, and feature status.

## User-facing tool integrations

### OpenHands coding workspaces

- [OpenHands / Agent Canvas source](https://github.com/OpenHands/OpenHands)
- [OpenHands local setup](https://docs.openhands.dev/openhands/usage/run-openhands/local-setup)
- [OpenHands self-hosting guide](https://github.com/OpenHands/OpenHands/blob/main/SELF_HOSTING.md)
- [Docker Engine API](https://docs.docker.com/reference/api/engine/)

Portal implementation: `backend/app/routes/ide.py`,
`backend/app/services/ide_service.py`, `frontend/src/pages/DeveloperWorkspace.jsx`,
`provisioner/`, `compose.openhands.yml`, and `scripts/openhands-local.sh`.

### PowerPoint generation

- [office-kit/pptx source and documentation](https://github.com/office-kit/pptx)
- [Office Open XML presentation format overview](https://learn.microsoft.com/en-us/office/open-xml/presentation/structure-of-a-presentationml-document)

The browser uses pinned `@office-kit/pptx` 0.12.0 to create an editable PPTX
download from the server-generated, citation-aware presentation specification.
Implementation: `backend/app/rag/presentation.py`, `backend/app/media/deck.py`,
and `frontend/src/utils/presentation.js`.

### Scientific calculations

- [fluids source](https://github.com/CalebBell/fluids)
- [fluids API documentation](https://fluids.readthedocs.io/)

The server uses pinned `fluids` 1.3.1 through a fixed operation allow list with
validated finite SI inputs. Implementation: `backend/app/agent_tools/fluids_tool.py`
and the `scientific_tool` node in `backend/app/rag/nodes.py`.

### Approval-note document editor

- [ONLYOFFICE Docs API concepts](https://api.onlyoffice.com/docs/docs-api/get-started/basic-concepts/)
- [ONLYOFFICE editor configuration](https://api.onlyoffice.com/docs/docs-api/usage-api/config/)
- [ONLYOFFICE callback handler](https://api.onlyoffice.com/docs/docs-api/usage-api/callback-handler/)
- [ONLYOFFICE force-save command](https://api.onlyoffice.com/docs/docs-api/additional-api/command-service/forcesave/)
- [ONLYOFFICE Document Server container](https://hub.docker.com/r/onlyoffice/documentserver)
- [python-docx documentation](https://python-docx.readthedocs.io/en/latest/)

Implementation: `frontend/src/components/OnlyOfficeEditor.jsx`,
`backend/app/services/onlyoffice_service.py`, and
`backend/app/services/docx_populate.py`.

## RAG design and implementation sources

### Foundational retrieval design

- [Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks
  (Lewis et al., NeurIPS 2020)](https://arxiv.org/abs/2005.11401)
- [Reciprocal Rank Fusion outperforms Condorcet and individual rank learning
  methods (Cormack, Clarke, and Buettcher, SIGIR 2009)](https://research.google/pubs/reciprocal-rank-fusion-outperforms-condorcet-and-individual-rank-learning-methods/)

The portal is not a copy of the paper's training architecture. It applies the
same retrieve-then-generate principle to application documents, combines dense
cosine and lexical results with Reciprocal Rank Fusion, reranks them, grades
evidence, and supplies only authorized chunks to the answer model.

### Agent orchestration

- [LangGraph source](https://github.com/langchain-ai/langgraph)
- [LangGraph `StateGraph` API](https://reference.langchain.com/python/langgraph/graph/state/StateGraph)

Implementation: `backend/app/rag/graph.py` and `backend/app/rag/nodes.py`.
The graph performs scope resolution, conversation contextualization, query
understanding, tool routing, retrieval, reranking, evidence grading, bounded
query rewriting, context construction, answer generation, claim verification,
general-knowledge fallback, and citation validation.

### LLM and embedding providers

- [OpenAI chat-completions API](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)
- [OpenAI embeddings guide](https://developers.openai.com/api/docs/guides/embeddings)
- [Ollama API](https://docs.ollama.com/api/introduction)
- [Ollama OpenAI compatibility](https://docs.ollama.com/api/openai-compatibility)
- [BGE-M3 model card](https://huggingface.co/BAAI/bge-m3)
- [BGE-M3 paper](https://arxiv.org/abs/2402.03216)

Implementation: `backend/app/rag/llm.py`, `backend/app/rag/reasoning.py`, and
`backend/app/rag/embeddings.py`. The dependency-free local defaults are a
deterministic hashing embedder and extractive/heuristic answer path. OpenAI,
Azure/OpenAI-compatible endpoints, Ollama, and vLLM are configurable providers.

### Vector storage and authorization filtering

- [Qdrant documentation](https://qdrant.tech/documentation/)
- [Qdrant payload filtering](https://qdrant.tech/documentation/search/filtering/)
- [Qdrant Python client](https://github.com/qdrant/qdrant-client)
- [SQLite documentation](https://www.sqlite.org/docs.html)

Implementation: `backend/app/rag/vector_store.py` and
`backend/app/services/authorization_service.py`. SQLite is the default local
vector store; Qdrant is selected with `VECTOR_STORE=qdrant`. Both apply the
owner/department/common visibility predicate before an item can enter reranking,
agent state, citations, or model context.

### Ingestion and parsing

- [pypdf documentation](https://pypdf.readthedocs.io/en/stable/)
- [python-docx documentation](https://python-docx.readthedocs.io/en/latest/)
- [openpyxl documentation](https://openpyxl.readthedocs.io/en/stable/)
- [Docling source](https://github.com/docling-project/docling) - optional richer
  structure-aware parser when installed.

Implementation: `backend/app/rag/ingestion.py` and
`backend/app/media/docling_parser.py`. The upload path accepts PDF, DOCX, XLSX,
CSV, Markdown, and TXT, then parses, chunks with overlap, embeds, stores inherited
authorization metadata, and indexes the chunks.

### Generated slide media and analytics

- [DuckDB documentation](https://duckdb.org/docs/stable/)
- [Vega-Lite documentation](https://vega.github.io/vega-lite/)
- [vl-convert source](https://github.com/vega/vl-convert)
- [Mermaid CLI source](https://github.com/mermaid-js/mermaid-cli)

Implementation: `backend/app/media/analytics.py`, `charts.py`, `diagrams.py`,
and `deck.py`. These add data aggregation, chart PNGs, and diagrams to PPTX
specifications and degrade gracefully when an optional renderer is unavailable.

## Application platform sources

- [FastAPI](https://fastapi.tiangolo.com/) and
  [Uvicorn](https://www.uvicorn.org/) - backend HTTP application and server.
- [SQLAlchemy](https://docs.sqlalchemy.org/en/20/) and
  [Pydantic](https://docs.pydantic.dev/latest/) - persistence and validation.
- [React](https://react.dev/), [React Router](https://reactrouter.com/), and
  [Vite](https://vite.dev/) - browser application and build tooling.
- [Lucide](https://lucide.dev/) and
  [Motion](https://motion.dev/docs/react) - interface icons and motion.
- [PyJWT](https://pyjwt.readthedocs.io/) and
  [argon2-cffi](https://argon2-cffi.readthedocs.io/) - JWT handling and Argon2id
  password hashing.
- [Docker](https://docs.docker.com/) - local ONLYOFFICE and isolated OpenHands
  runtime deployment.

## What is active versus available

The implementation supports multiple providers, but provider selection is
environment-specific. In the checked local configuration, the answer/reasoning
provider is OpenAI-compatible, OpenHands and ONLYOFFICE are enabled, and unset
RAG provider values use the repository defaults: hashing embeddings, SQLite
vector storage, and lexical reranking. Qdrant, Ollama/BGE-M3, and Docling are
implemented options, not claims that those external services are active in
every deployment.
