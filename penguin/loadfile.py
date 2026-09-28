"""Parsers for the load files that accompany an eDiscovery production.

Two formats matter here:

* Concordance DAT - the metadata file. Fields are separated by ASCII 20
  and quoted with ASCII 254. Those characters are used because they are
  vanishingly rare inside real document text, unlike commas and quotes.
* Opticon OPT - the image cross-reference file. One comma-delimited line
  per page, marking which pages begin a document.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from pathlib import Path

# Concordance delimiters, by convention.
FIELD_SEP = "\x14"  # ASCII 20, shown in documentation as the pilcrow
QUOTE_CHAR = "\xfe"  # ASCII 254, shown as thorn
MULTI_SEP = ";"  # separator inside a single field, e.g. multiple custodians


class LoadFileError(Exception):
    """Raised when a load file cannot be parsed at all."""


@dataclass
class DatRecord:
    """One row of a Concordance DAT file."""

    row: int
    fields: dict[str, str]

    def get(self, name: str, default: str = "") -> str:
        return self.fields.get(name, default).strip()

    def multi(self, name: str) -> list[str]:
        raw = self.get(name)
        if not raw:
            return []
        return [part.strip() for part in raw.split(MULTI_SEP) if part.strip()]


@dataclass
class DatFile:
    path: Path
    columns: list[str]
    records: list[DatRecord] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.records)


@dataclass
class OptPage:
    """One page entry from an Opticon file."""

    row: int
    image_key: str
    volume: str
    relative_path: str
    doc_break: bool
    pages: int | None


@dataclass
class OptFile:
    path: Path
    pages: list[OptPage] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.pages)

    def document_keys(self) -> list[str]:
        return [page.image_key for page in self.pages if page.doc_break]


def read_dat(path: str | Path, encoding: str = "utf-8-sig") -> DatFile:
    """Read a Concordance DAT file into records.

    The file is read with the Python csv module, pointed at the
    Concordance delimiters rather than commas.
    """
    path = Path(path)
    try:
        text = path.read_text(encoding=encoding)
    except UnicodeDecodeError as exc:
        raise LoadFileError(
            f"{path.name} is not valid {encoding}. Productions are commonly "
            f"delivered as UTF-16 or Windows-1252; re-run with --encoding."
        ) from exc

    reader = csv.reader(
        io.StringIO(text, newline=""),
        delimiter=FIELD_SEP,
        quotechar=QUOTE_CHAR,
        doublequote=False,
        strict=False,
    )
    rows = [row for row in reader if any(cell.strip() for cell in row)]
    if not rows:
        raise LoadFileError(f"{path.name} contains no rows.")

    header = [col.strip() for col in rows[0]]
    records: list[DatRecord] = []
    for index, row in enumerate(rows[1:], start=2):
        # Pad or trim so a short row does not silently shift every field.
        cells = list(row[: len(header)])
        cells += [""] * (len(header) - len(cells))
        records.append(DatRecord(row=index, fields=dict(zip(header, cells))))

    return DatFile(path=path, columns=header, records=records)


def read_opt(path: str | Path, encoding: str = "utf-8-sig") -> OptFile:
    """Read an Opticon image load file."""
    path = Path(path)
    pages: list[OptPage] = []
    with path.open("r", encoding=encoding, newline="") as handle:
        for index, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            parts = line.split(",")
            if len(parts) < 4:
                raise LoadFileError(
                    f"{path.name} line {index} has {len(parts)} columns; "
                    f"an Opticon line needs at least 4."
                )
            page_count: int | None = None
            if len(parts) >= 7 and parts[6].strip():
                try:
                    page_count = int(parts[6])
                except ValueError:
                    page_count = None
            pages.append(
                OptPage(
                    row=index,
                    image_key=parts[0].strip(),
                    volume=parts[1].strip(),
                    relative_path=parts[2].strip(),
                    doc_break=parts[3].strip().upper() == "Y",
                    pages=page_count,
                )
            )
    return OptFile(path=path, pages=pages)
