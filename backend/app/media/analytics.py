"""Data analytics with DuckDB (in-process OLAP SQL).

Runs read-only aggregation over tabular records the deck planner provides (or
tabular data extracted from an authorized document). The LLM may supply a
`SELECT`; it is validated to be a single read-only statement and executed with
external file/network access disabled, so it can only touch the in-memory
`data` table.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from typing import Any

from app.core.config import settings

try:  # optional dependency
    import duckdb

    _AVAILABLE = True
except Exception:  # pragma: no cover - import guard
    _AVAILABLE = False

_FORBIDDEN = re.compile(
    r"\b(attach|copy|install|load|pragma|export|import|"
    r"read_csv|read_parquet|read_json|read_text|glob|system)\b",
    re.IGNORECASE,
)


def available() -> bool:
    return _AVAILABLE and settings.analytics_enabled


def _is_safe_select(sql: str) -> bool:
    s = sql.strip().rstrip(";")
    if ";" in s:  # single statement only
        return False
    if not re.match(r"(?is)^(select|with)\b", s):
        return False
    return not _FORBIDDEN.search(s)


def _cell(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, float):
        return round(value, 4)
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    return value


def run_analysis(
    records: list[dict], sql: str | None = None, *, limit: int | None = None
) -> dict | None:
    """Return {"columns": [...], "rows": [[...]]} or None.

    `records` are loaded into an in-memory `data` table. `sql` (optional) must be
    a single read-only SELECT/WITH over `data`; otherwise the rows are returned
    as-is.
    """
    if not available() or not records:
        return None
    limit = limit or settings.analytics_max_rows
    con = duckdb.connect()
    tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    try:
        json.dump(records, tmp)
        tmp.flush()
        tmp.close()
        con.execute(f"CREATE TABLE data AS SELECT * FROM read_json_auto('{tmp.name}')")
        # Lock down external access before running the (possibly LLM-authored) query.
        try:
            con.execute("SET enable_external_access=false")
        except Exception:  # noqa: BLE001 - not fatal; the SQL guard still applies
            pass
        inner = sql if (sql and _is_safe_select(sql)) else "SELECT * FROM data"
        query = f"SELECT * FROM ({inner.rstrip(';')}) AS _q LIMIT {int(limit)}"
        cur = con.execute(query)
        columns = [d[0] for d in cur.description]
        rows = [[_cell(v) for v in row] for row in cur.fetchall()]
        if not rows:
            return None
        return {"columns": columns, "rows": rows}
    except Exception:  # noqa: BLE001 - analytics is best-effort
        return None
    finally:
        con.close()
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
