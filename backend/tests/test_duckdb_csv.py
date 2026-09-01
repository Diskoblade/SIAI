"""Example DuckDB test: load a CSV, run an aggregation through the app's
analytics layer (app.media.analytics.run_analysis), and assert the results.

Run just this file:
    ./.venv/bin/python -m pytest tests/test_duckdb_csv.py -v
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from app.media import analytics

CSV_PATH = Path(__file__).resolve().parents[1] / "sample_data" / "department_spend.csv"


def _load_records() -> list[dict]:
    """Read the CSV into records (list of dicts), coercing amount to int."""
    with CSV_PATH.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    for row in rows:
        row["amount"] = int(row["amount"])
    return rows


@pytest.fixture(scope="module")
def records() -> list[dict]:
    if not analytics.available():
        pytest.skip("duckdb not installed")
    return _load_records()


def test_total_spend_by_department(records):
    """SUM(amount) grouped by department, highest first."""
    result = analytics.run_analysis(
        records,
        "SELECT department, SUM(amount) AS total_spend "
        "FROM data GROUP BY department ORDER BY total_spend DESC",
    )
    assert result["columns"] == ["department", "total_spend"]
    # Engineering: 210000 + 95000 + 240000 = 545000  (the top spender)
    assert result["rows"][0] == ["Engineering", 545000]
    # Finance: 120000 + 45000 + 98000 = 263000
    finance = next(r for r in result["rows"] if r[0] == "Finance")
    assert finance[1] == 263000
    assert len(result["rows"]) == 5  # five departments


def test_spend_by_quarter(records):
    """Total spend per quarter."""
    result = analytics.run_analysis(
        records,
        "SELECT quarter, SUM(amount) AS total FROM data GROUP BY quarter ORDER BY quarter",
    )
    totals = {row[0]: row[1] for row in result["rows"]}
    assert totals["Q1"] == 635000
    assert totals["Q2"] == 516000


def test_top_category_with_cte(records):
    """A WITH (CTE) query is allowed (read-only)."""
    result = analytics.run_analysis(
        records,
        "WITH by_cat AS (SELECT category, SUM(amount) AS s FROM data GROUP BY category) "
        "SELECT category, s FROM by_cat ORDER BY s DESC LIMIT 1",
    )
    assert result["rows"][0][0] == "Cloud"  # 210000 + 240000 = 450000
    assert result["rows"][0][1] == 450000


def test_destructive_sql_is_ignored(records):
    """A non-SELECT statement is refused; it falls back to returning the rows."""
    result = analytics.run_analysis(records, "DROP TABLE data")
    assert result is not None
    assert "department" in result["columns"]  # plain rows, table intact
