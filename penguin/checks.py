"""Validation rules run against a production before it goes out the door.

Each rule returns Exception records. Nothing here mutates the production;
the output is a list of findings a human reviews and signs off on, which
is the only way QC results are useful in a dispute.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import bates as bates_mod
from .loadfile import DatFile, OptFile

BLOCKER = "blocker"
WARNING = "warning"

# Fields a production is normally required to carry. Protocols vary, so this
# is the default and can be overridden from the CLI.
DEFAULT_REQUIRED_FIELDS = [
    "BegDoc",
    "EndDoc",
    "Custodian",
    "DocDate",
    "FileName",
]

DATE_FORMATS = ["%m/%d/%Y", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y %H:%M", "%Y-%m-%d %H:%M:%S"]

CONTROL_CHARS = {chr(code) for code in range(0, 32)} - {"\t"}


@dataclass
class Finding:
    rule: str
    severity: str
    record: str
    detail: str

    @property
    def is_blocker(self) -> bool:
        return self.severity == BLOCKER


@dataclass
class ProductionSummary:
    records: int = 0
    documents_with_images: int = 0
    opt_pages: int = 0
    families: int = 0
    natives_expected: int = 0
    natives_found: int = 0
    text_expected: int = 0
    text_found: int = 0
    bates_first: str = ""
    bates_last: str = ""
    custodians: list[str] = field(default_factory=list)


def _parse_date(value: str) -> datetime | None:
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def check_required_fields(
    dat: DatFile, required: list[str] | None = None
) -> list[Finding]:
    required = required or DEFAULT_REQUIRED_FIELDS
    present = {col.lower() for col in dat.columns}
    return [
        Finding(
            rule="required-field",
            severity=BLOCKER,
            record=dat.path.name,
            detail=f"Load file has no {name} column.",
        )
        for name in required
        if name.lower() not in present
    ]


def check_bates(dat: DatFile) -> tuple[list[Finding], list[bates_mod.Bates]]:
    findings: list[Finding] = []
    begins: list[bates_mod.Bates] = []
    # Every number the production actually consumes, including the interior
    # pages of multi-page documents. Gaps are found against this, not against
    # consecutive BegDoc values, or every multi-page document reads as a gap.
    consumed: list[bates_mod.Bates] = []

    for record in dat.records:
        begin_raw = record.get("BegDoc")
        end_raw = record.get("EndDoc")

        if not begin_raw:
            findings.append(
                Finding("bates-missing", BLOCKER, f"row {record.row}", "BegDoc is empty.")
            )
            continue

        begin = bates_mod.parse(begin_raw)
        if begin is None:
            findings.append(
                Finding(
                    "bates-malformed",
                    BLOCKER,
                    begin_raw,
                    "BegDoc does not end in a numeric sequence.",
                )
            )
            continue
        begins.append(begin)
        consumed.append(begin)

        if end_raw:
            end = bates_mod.parse(end_raw)
            if end is None:
                findings.append(
                    Finding(
                        "bates-malformed", BLOCKER, begin_raw,
                        f"EndDoc {end_raw!r} does not end in a numeric sequence.",
                    )
                )
            elif end.prefix != begin.prefix:
                findings.append(
                    Finding(
                        "bates-range", BLOCKER, begin_raw,
                        f"BegDoc and EndDoc use different prefixes "
                        f"({begin.prefix!r} and {end.prefix!r}).",
                    )
                )
            elif end.number < begin.number:
                findings.append(
                    Finding(
                        "bates-range", BLOCKER, begin_raw,
                        f"EndDoc {end.text} precedes BegDoc.",
                    )
                )
            else:
                width = max(begin.width, end.width)
                consumed.extend(
                    bates_mod.Bates(begin.prefix, number, width)
                    for number in range(begin.number + 1, end.number + 1)
                )

    for text, count in bates_mod.find_duplicates(begins).items():
        findings.append(
            Finding("bates-duplicate", BLOCKER, text, f"BegDoc appears {count} times.")
        )

    for gap in bates_mod.find_gaps(consumed):
        findings.append(
            Finding(
                "bates-gap",
                WARNING,
                gap.after,
                f"{gap.missing} number(s) missing before {gap.before}.",
            )
        )

    return findings, begins


def check_families(dat: DatFile) -> list[Finding]:
    """Attachments must point at a parent that is actually in the production."""
    findings: list[Finding] = []
    known = {record.get("BegDoc") for record in dat.records if record.get("BegDoc")}

    for record in dat.records:
        begin = record.get("BegDoc") or f"row {record.row}"
        parent = record.get("BegAttach")
        if not parent:
            continue
        if parent not in known:
            findings.append(
                Finding(
                    "family-orphan",
                    BLOCKER,
                    begin,
                    f"BegAttach points at {parent}, which is not in this production.",
                )
            )
            continue

        end_attach = record.get("EndAttach")
        this_doc = bates_mod.parse(begin)
        parent_bates = bates_mod.parse(parent)
        if this_doc and parent_bates and this_doc.number < parent_bates.number:
            findings.append(
                Finding(
                    "family-order",
                    WARNING,
                    begin,
                    f"Document sorts before its parent {parent}.",
                )
            )
        if end_attach:
            end_bates = bates_mod.parse(end_attach)
            if end_bates and this_doc and end_bates.number < this_doc.number:
                findings.append(
                    Finding(
                        "family-range",
                        BLOCKER,
                        begin,
                        f"EndAttach {end_attach} precedes the document itself.",
                    )
                )
    return findings


def check_linked_files(dat: DatFile, root: Path) -> tuple[list[Finding], dict[str, int]]:
    """Every native and text link in the DAT must resolve to a real file."""
    findings: list[Finding] = []
    counts = {"natives_expected": 0, "natives_found": 0, "text_expected": 0, "text_found": 0}

    for record in dat.records:
        begin = record.get("BegDoc") or f"row {record.row}"

        for column, kind in (("NativeLink", "native"), ("TextLink", "text")):
            link = record.get(column)
            if not link:
                continue
            counts[f"{'natives' if kind == 'native' else 'text'}_expected"] += 1
            target = root / link.replace("\\", "/").lstrip("/")
            if not target.exists():
                findings.append(
                    Finding(
                        f"{kind}-missing",
                        BLOCKER,
                        begin,
                        f"{column} points at {link}, which is not in the volume.",
                    )
                )
                continue
            counts[f"{'natives' if kind == 'native' else 'text'}_found"] += 1
            if kind == "text" and target.stat().st_size == 0:
                findings.append(
                    Finding(
                        "text-empty",
                        WARNING,
                        begin,
                        f"Extracted text file {link} is zero bytes.",
                    )
                )
    return findings, counts


def check_images(dat: DatFile, opt: OptFile | None) -> list[Finding]:
    """Cross-check the metadata file against the image load file."""
    if opt is None:
        return []

    findings: list[Finding] = []
    dat_keys = {record.get("BegDoc") for record in dat.records if record.get("BegDoc")}
    opt_docs = set(opt.document_keys())

    for key in sorted(opt_docs - dat_keys):
        findings.append(
            Finding(
                "image-orphan",
                BLOCKER,
                key,
                "Image load file contains a document that is not in the DAT.",
            )
        )

    pages_by_doc: dict[str, int] = {}
    current: str | None = None
    for page in opt.pages:
        if page.doc_break:
            current = page.image_key
        if current:
            pages_by_doc[current] = pages_by_doc.get(current, 0) + 1

    for record in dat.records:
        begin = record.get("BegDoc")
        stated = record.get("PageCount")
        if not begin or not stated:
            continue
        try:
            expected = int(stated)
        except ValueError:
            findings.append(
                Finding("page-count", WARNING, begin, f"PageCount {stated!r} is not a number.")
            )
            continue
        actual = pages_by_doc.get(begin)
        if actual is None:
            findings.append(
                Finding(
                    "image-missing",
                    BLOCKER,
                    begin,
                    f"DAT states {expected} page(s) but the document has no images.",
                )
            )
        elif actual != expected:
            findings.append(
                Finding(
                    "page-count",
                    BLOCKER,
                    begin,
                    f"DAT states {expected} page(s); image load file has {actual}.",
                )
            )
    return findings


def check_field_hygiene(dat: DatFile) -> list[Finding]:
    """Dates that will not parse, and control characters that break downstream loads."""
    findings: list[Finding] = []
    for record in dat.records:
        begin = record.get("BegDoc") or f"row {record.row}"

        date_value = record.get("DocDate")
        if date_value and _parse_date(date_value) is None:
            findings.append(
                Finding("date-format", WARNING, begin, f"DocDate {date_value!r} did not parse.")
            )

        for column, value in record.fields.items():
            if any(char in CONTROL_CHARS for char in value):
                findings.append(
                    Finding(
                        "control-character",
                        BLOCKER,
                        begin,
                        f"{column} contains an unescaped control character.",
                    )
                )
    return findings


def check_confidentiality(dat: DatFile) -> list[Finding]:
    """A designated document must carry the endorsement text."""
    if "Confidentiality" not in dat.columns:
        return []
    findings: list[Finding] = []
    for record in dat.records:
        designation = record.get("Confidentiality")
        if not designation:
            continue
        endorsement = record.get("Endorsement")
        if not endorsement:
            findings.append(
                Finding(
                    "endorsement-missing",
                    BLOCKER,
                    record.get("BegDoc") or f"row {record.row}",
                    f"Designated {designation!r} but carries no endorsement text.",
                )
            )
    return findings


def summarize(dat: DatFile, opt: OptFile | None, link_counts: dict[str, int]) -> ProductionSummary:
    begins = [b for b in (bates_mod.parse(r.get("BegDoc")) for r in dat.records) if b]
    ordered = sorted(begins)
    custodians: set[str] = set()
    for record in dat.records:
        custodians.update(record.multi("Custodian"))

    return ProductionSummary(
        records=len(dat),
        documents_with_images=len(opt.document_keys()) if opt else 0,
        opt_pages=len(opt) if opt else 0,
        families=sum(1 for r in dat.records if r.get("BegAttach")),
        natives_expected=link_counts.get("natives_expected", 0),
        natives_found=link_counts.get("natives_found", 0),
        text_expected=link_counts.get("text_expected", 0),
        text_found=link_counts.get("text_found", 0),
        bates_first=ordered[0].text if ordered else "",
        bates_last=ordered[-1].text if ordered else "",
        custodians=sorted(custodians),
    )


def run_all(
    dat: DatFile,
    opt: OptFile | None,
    root: Path,
    required: list[str] | None = None,
) -> tuple[list[Finding], ProductionSummary]:
    findings: list[Finding] = []
    findings += check_required_fields(dat, required)
    bates_findings, _ = check_bates(dat)
    findings += bates_findings
    findings += check_families(dat)
    link_findings, link_counts = check_linked_files(dat, root)
    findings += link_findings
    findings += check_images(dat, opt)
    findings += check_field_hygiene(dat)
    findings += check_confidentiality(dat)
    return findings, summarize(dat, opt, link_counts)
