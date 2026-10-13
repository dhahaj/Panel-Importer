"""Optional BOM CSV: only the designators are used, to cross-check against ODB++.

The header row is found by its designator column (``Designator``, ``RefDes``,
``Reference``, ``Ref Des``...), which skips any title block above it.  A cell may
list several designators (``C1, C2, C3``), as Altium groups them.
"""

from __future__ import annotations

import csv
import io
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

DESIGNATOR_HEADERS = ("designator", "designators", "refdes", "ref des", "reference", "references", "ref", "part reference")
_SPLIT = re.compile(r"[,;\s]+")


class BomError(Exception):
    pass


@dataclass
class Bom:
    path: str
    designators: list[str] = field(default_factory=list)
    column: str = ""
    rows: int = 0


def read_bom(path: str | os.PathLike) -> Bom:
    raw = Path(path).read_bytes()
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.reader(io.StringIO(text), dialect))
    header_idx = col = None
    for i, row in enumerate(rows):
        for j, cell in enumerate(row):
            if cell.strip().strip('"').lower() in DESIGNATOR_HEADERS:
                header_idx, col = i, j
                break
        if header_idx is not None:
            break
    if header_idx is None or col is None:
        raise BomError(f"{path}: no designator column found (looked for {', '.join(DESIGNATOR_HEADERS)})")
    bom = Bom(path=str(path), column=rows[header_idx][col].strip())
    seen = set()
    for row in rows[header_idx + 1 :]:
        if col >= len(row):
            continue
        cell = row[col].strip()
        if not cell:
            continue
        bom.rows += 1
        for token in _SPLIT.split(cell):
            token = token.strip().strip('"')
            if token and token not in seen:
                seen.add(token)
                bom.designators.append(token)
    return bom
