"""Row-oriented ingestion for spreadsheets (xlsx) and CSV.

Each data row becomes one self-describing "Column: value | ..." block so it
stays meaningful after chunking and retrieves on any column value.
"""

from __future__ import annotations

import io

from openpyxl import Workbook

from app.rag import ingestion
from app.rag.ingestion import _cap_cell


def _xlsx(rows: list[list]) -> bytes:
    wb = Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_xlsx_rows_are_self_describing():
    data = _xlsx(
        [
            ["Course", "Code", "Credit", "Duration"],
            ["Data Analytics", "ONL1038", "3", "12 Weeks"],
            ["Machine Learning", "ONL2003", "3", "8 Weeks"],
        ]
    )
    blocks = ingestion.parse_document("courses.xlsx", data)
    assert len(blocks) == 2  # one block per data row (header excluded)
    text = blocks[0].text
    assert "Course: Data Analytics" in text
    assert "Code: ONL1038" in text
    assert "Credit: 3" in text and "Duration: 12 Weeks" in text


def test_csv_rows_are_self_describing():
    data = b"Course,Code,Credit\nData Analytics,ONL1038,3\nMachine Learning,ONL2003,3\n"
    blocks = ingestion.parse_document("courses.csv", data)
    assert len(blocks) == 2
    assert "Course: Data Analytics" in blocks[0].text
    assert "Credit: 3" in blocks[0].text


def test_section_banner_becomes_heading():
    data = _xlsx(
        [
            ["Name", "Value"],
            ["Section A", None],  # single-cell banner row
            ["item1", "10"],
        ]
    )
    blocks = ingestion.parse_document("s.xlsx", data)
    assert any("Section A" in b.text for b in blocks)
    assert any("Name: item1" in b.text and "Value: 10" in b.text for b in blocks)


def test_long_cell_is_capped():
    capped = _cap_cell("x" * 300)
    assert capped.endswith("…")
    assert len(capped) <= 160
    # short values are untouched
    assert _cap_cell("ONL1038") == "ONL1038"


def test_xlsx_not_routed_through_docling():
    # Spreadsheets must use the row parser, not Docling's markdown table.
    from app.media import docling_parser

    assert ".xlsx" not in docling_parser.SUPPORTED
    assert ".csv" not in docling_parser.SUPPORTED
