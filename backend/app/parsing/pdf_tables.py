"""pdfplumber table extraction."""

from __future__ import annotations

from pathlib import Path

import pdfplumber

from backend.app.schemas.document import TableInfo


def extract_tables(path: Path | str) -> list[TableInfo]:
    tables: list[TableInfo] = []
    with pdfplumber.open(path) as pdf:
        for page_idx, page in enumerate(pdf.pages):
            for table in page.extract_tables() or []:
                if not table:
                    continue
                headers = [str(c or "") for c in table[0]]
                rows = [[str(c or "") for c in row] for row in table[1:]]
                tables.append(TableInfo(page=page_idx + 1, headers=headers, rows=rows))
    return tables
