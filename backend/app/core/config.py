"""Application configuration.

All secrets and environment-specific values are read from environment
variables (loaded from a local `.env` during development). Nothing sensitive
is hard-coded here.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- App ---
    app_name: str = "Sovereign Knowledge Portal"

    # --- Database ---
    # SQLite for the prototype. Structured so switching to PostgreSQL only
    # requires changing this URL (see database.py for the engine handling).
    database_url: str = "sqlite:///./sih.db"

    # --- JWT ---
    jwt_secret_key: str = "change-this-secret-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30

    # --- CORS ---
    # Comma-separated list of allowed frontend origins.
    frontend_url: str = "http://localhost:5173"

    # ------------------------------------------------------------------ #
    # RAG platform (Milestone 1+). Providers are pluggable; the defaults
    # are fully local and require no external services or model downloads,
    # so every milestone stays runnable. Flip these to use Ollama/Qdrant.
    # ------------------------------------------------------------------ #

    # Embeddings: "hashing" (default, dependency-free) | "ollama" (local bge-m3)
    # | "openai" (hosted, e.g. OpenAI text-embedding-3-small — no local model)
    embedding_provider: str = "hashing"
    embedding_dim: int = 512  # only used by the hashing embedder
    ollama_base_url: str = "http://localhost:11434"
    ollama_embedding_model: str = "bge-m3"
    # OpenAI-compatible embeddings (OpenAI cloud, Azure OpenAI, etc.)
    embedding_base_url: str = "https://api.openai.com/v1"
    embedding_api_key: str = ""
    embedding_model: str = "text-embedding-3-small"

    # Vector store: "sqlite" (default, in-DB cosine) | "qdrant"
    vector_store: str = "sqlite"
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "documents"

    # Answer + reasoning LLM:
    #   "extractive" (default, deterministic, no LLM call — agentic nodes use
    #                 heuristic fallbacks so the graph runs fully offline)
    #   "openai"     (any OpenAI-compatible /chat/completions: OpenAI/ChatGPT,
    #                 Azure OpenAI, Ollama /v1, vLLM). This also powers the
    #                 agentic reasoning nodes.
    llm_provider: str = "extractive"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    # When authorized retrieval cannot produce sufficient evidence, allow the
    # configured LLM to answer from general model knowledge. The response is
    # explicitly marked as ungrounded and never receives document citations.
    rag_general_knowledge_fallback_enabled: bool = True

    # Server-side scientific calculation tools. Tool execution is restricted to
    # the allow-listed operations in app.agent_tools; no arbitrary Python runs.
    fluids_tool_enabled: bool = True

    # Reranker: "lexical" (default, deterministic) | "bge" (local cross-encoder)
    reranker_provider: str = "lexical"
    bge_reranker_model: str = "BAAI/bge-reranker-v2-m3"

    # Retrieval knobs (all configurable per spec).
    retrieval_candidates: int = 30  # hybrid candidate pool
    rerank_top_k: int = 6           # kept after reranking
    max_retrieval_retries: int = 2  # query-rewrite loop cap
    # Minimum reranked relevance for evidence to count as sufficient (grader
    # fallback when no reasoning LLM is configured).
    evidence_sufficiency_threshold: float = 0.15

    # --- Deck media generation (charts / diagrams / analytics / parsing) ---
    # Charts: Vega-Lite specs rendered to PNG via vl-convert (no browser).
    charts_enabled: bool = True
    # Diagrams: Mermaid rendered to PNG via mermaid-cli (mmdc, headless Chrome).
    diagrams_enabled: bool = True
    # Path to the mermaid-cli binary; default points at backend/tools install.
    mermaid_cli_path: str = "tools/node_modules/.bin/mmdc"
    # Analytics: DuckDB in-memory SQL over LLM-provided/authorized tabular data.
    analytics_enabled: bool = True
    analytics_max_rows: int = 100
    # Docling: preferred document parser when installed (falls back otherwise).
    docling_enabled: bool = True
    # Cap the number of rendered visual (image/table) slides per deck.
    deck_max_visuals: int = 4

    # --- Browser coding workspace (OpenHands Agent Canvas) ---
    # The portal calls an internal provisioner which creates or resolves one
    # isolated Agent Server workspace per user. Secrets stay server-side.
    openhands_enabled: bool = False
    openhands_provisioner_url: str = ""
    openhands_provisioner_api_key: str = ""
    openhands_public_url: str = ""
    openhands_request_timeout_seconds: float = 30.0

    # --- ONLYOFFICE Approval Notes ---
    # The app is single-tenant; every Approval Note row carries this company id
    # so multi-tenancy is a later, non-breaking change. Never taken from a request.
    default_company_id: int = 1
    # Private, backend-controlled storage root for letterheads and working DOCX.
    document_storage_dir: str = "storage"
    max_docx_upload_bytes: int = 25 * 1024 * 1024  # 25 MB

    # ONLYOFFICE Document Server (Community Edition, run via docker-compose).
    onlyoffice_enabled: bool = False
    # Browser-facing editor origin (loads the editor <script> and API).
    onlyoffice_url: str = "http://localhost:8085"
    # How the Document Server (in Docker) reaches THIS backend for file fetch +
    # callbacks. On macOS/Windows Docker Desktop use host.docker.internal.
    app_base_url_for_onlyoffice: str = "http://host.docker.internal:8010"
    # Shared secret for signing/validating ONLYOFFICE JWTs (server-side only).
    onlyoffice_jwt_secret: str = ""
    onlyoffice_request_timeout_seconds: float = 30.0

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.frontend_url.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (read once per process)."""
    return Settings()


settings = get_settings()
