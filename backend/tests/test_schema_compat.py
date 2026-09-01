"""Non-destructive prototype schema compatibility migration tests."""

from sqlalchemy import create_engine, inspect, text

from app.schema_compat import ensure_private_knowledge_columns


def test_existing_document_tables_gain_private_metadata_without_visibility_change():
    legacy = create_engine("sqlite:///:memory:")
    with legacy.begin() as connection:
        connection.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
        connection.execute(
            text(
                "CREATE TABLE documents ("
                "id VARCHAR(36) PRIMARY KEY, created_by INTEGER, document_type VARCHAR(80))"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE document_chunks ("
                "id VARCHAR(36) PRIMARY KEY, document_id VARCHAR(36))"
            )
        )
        connection.execute(text("INSERT INTO users (id) VALUES (7)"))
        connection.execute(
            text(
                "INSERT INTO documents (id, created_by, document_type) "
                "VALUES ('doc-1', 7, 'document')"
            )
        )
        connection.execute(
            text("INSERT INTO document_chunks (id, document_id) VALUES ('chunk-1', 'doc-1')")
        )

    assert ensure_private_knowledge_columns(legacy) is True

    document_columns = {column["name"] for column in inspect(legacy).get_columns("documents")}
    chunk_columns = {
        column["name"] for column in inspect(legacy).get_columns("document_chunks")
    }
    assert {"owner_user_id", "visibility", "shared_at", "memory_category"} <= document_columns
    assert {"owner_user_id", "visibility", "document_type", "memory_category"} <= chunk_columns

    with legacy.connect() as connection:
        document = connection.execute(
            text("SELECT owner_user_id, visibility FROM documents WHERE id = 'doc-1'")
        ).one()
        chunk = connection.execute(
            text(
                "SELECT owner_user_id, visibility, document_type "
                "FROM document_chunks WHERE id = 'chunk-1'"
            )
        ).one()
    assert document.owner_user_id == 7
    assert document.visibility is None
    assert chunk.owner_user_id == 7
    assert chunk.visibility is None
    assert chunk.document_type == "document"
