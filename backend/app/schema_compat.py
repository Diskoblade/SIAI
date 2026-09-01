"""Small non-destructive compatibility migration for the SQLite prototype.

The project does not use Alembic yet. `create_all()` cannot add columns to an
existing table, so startup adds only the new nullable metadata columns and
backfills ownership from the existing `created_by` field. Existing visibility
is intentionally left null so legacy access-scope behavior is preserved.
"""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def _columns(engine: Engine, table: str) -> set[str]:
    return {column["name"] for column in inspect(engine).get_columns(table)}


def ensure_private_knowledge_columns(engine: Engine) -> bool:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "documents" not in tables or "document_chunks" not in tables:
        return False

    document_columns = {
        "owner_user_id": "INTEGER REFERENCES users(id)",
        "visibility": "VARCHAR(20)",
        "shared_at": "TIMESTAMP",
        "memory_category": "VARCHAR(40)",
    }
    chunk_columns = {
        "owner_user_id": "INTEGER",
        "visibility": "VARCHAR(20)",
        "document_type": "VARCHAR(80) DEFAULT 'document'",
        "memory_category": "VARCHAR(40)",
    }

    changed = False
    with engine.begin() as connection:
        existing = _columns(engine, "documents")
        for name, column_type in document_columns.items():
            if name not in existing:
                connection.execute(text(f"ALTER TABLE documents ADD COLUMN {name} {column_type}"))
                changed = True

        existing_chunks = _columns(engine, "document_chunks")
        for name, column_type in chunk_columns.items():
            if name not in existing_chunks:
                connection.execute(
                    text(f"ALTER TABLE document_chunks ADD COLUMN {name} {column_type}")
                )
                changed = True

        connection.execute(
            text(
                "UPDATE documents SET owner_user_id = created_by "
                "WHERE owner_user_id IS NULL AND created_by IS NOT NULL"
            )
        )
        connection.execute(
            text(
                "UPDATE document_chunks SET owner_user_id = "
                "(SELECT owner_user_id FROM documents "
                " WHERE documents.id = document_chunks.document_id) "
                "WHERE owner_user_id IS NULL"
            )
        )
        connection.execute(
            text(
                "UPDATE document_chunks SET document_type = "
                "(SELECT document_type FROM documents "
                " WHERE documents.id = document_chunks.document_id) "
                "WHERE document_type IS NULL OR document_type = ''"
            )
        )

        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_documents_owner_user_id "
                "ON documents (owner_user_id)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_documents_visibility "
                "ON documents (visibility)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_document_chunks_owner_user_id "
                "ON document_chunks (owner_user_id)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_document_chunks_visibility "
                "ON document_chunks (visibility)"
            )
        )
    return changed
