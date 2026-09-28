"""Build a synthetic production volume, with defects, for demos and tests.

Everything here is invented. No client data, no real custodians. The
defects are the ones that actually turn up in delivered productions:
a gap where documents were culled after the Bates range was assigned,
a native that never made it into the volume, an attachment whose parent
was withheld, a page count that drifted.
"""

from __future__ import annotations

import random
from pathlib import Path

from penguin.loadfile import FIELD_SEP, QUOTE_CHAR

COLUMNS = [
    "BegDoc", "EndDoc", "BegAttach", "EndAttach", "Custodian", "DocDate",
    "Author", "FileName", "FileExt", "PageCount", "Confidentiality",
    "Endorsement", "NativeLink", "TextLink",
]

CUSTODIANS = ["Adeyemi, N.", "Baptiste, R.", "Cho, W.", "Duarte, M.", "Whitfield, J."]
AUTHORS = ["n.adeyemi", "r.baptiste", "w.cho", "m.duarte", "j.whitfield"]

SUBJECTS = [
    "Q3 vendor reconciliation", "Revised supplier terms", "Site visit notes",
    "Invoice dispute - Northbridge", "Board pre-read", "Rebate accrual memo",
    "Capacity forecast", "Audit request list", "Contract redlines",
    "Weekly ops summary", "Freight variance", "Inventory writedown",
]

DOMAINS = ["meridian-supply.example", "hensley-logistics.example", "calder-group.example"]

# Deliberately uneven: a few terms should hit a handful of documents, one
# should hit almost nothing, one should hit nearly everything. A term list
# where every term behaves the same demonstrates nothing.
COMMON_SNIPPETS = [
    "Flagging this before the close so there is a record of the question.",
    "Please hold the invoice until procurement confirms the revised terms.",
    "Confirming the site visit is moved to the following week.",
    "Attaching the schedule. Let me know if the format does not work.",
    "Adding the ops team so everyone is working from the same numbers.",
    "Short turnaround on this one. Flagging early rather than late.",
]

RARE_SNIPPETS = [
    "Per our call, the rebate accrual was booked against the wrong period.",
    "The variance sits entirely in the freight line, not in unit cost.",
    "Northbridge is disputing the charge again. Third time this quarter.",
    "Finance wants the write-down recognised this quarter, not next.",
    "I do not think we should put this in writing until legal weighs in.",
    "The audit request list arrived. Most of it we can answer from the ledger.",
    "The forecast assumes the Hensley contract renews. It may not.",
]


def _quote(value: str) -> str:
    return f"{QUOTE_CHAR}{value}{QUOTE_CHAR}"


def _row(values: list[str]) -> str:
    return FIELD_SEP.join(_quote(value) for value in values)


def build(root: str | Path, documents: int = 60, seed: int = 7) -> Path:
    """Create a production volume under ``root`` and return the path."""
    rng = random.Random(seed)
    root = Path(root)
    (root / "NATIVES").mkdir(parents=True, exist_ok=True)
    (root / "TEXT").mkdir(parents=True, exist_ok=True)
    (root / "IMAGES").mkdir(parents=True, exist_ok=True)

    prefix = "NBRG-"
    width = 7
    dat_rows: list[str] = [FIELD_SEP.join(_quote(col) for col in COLUMNS)]
    opt_lines: list[str] = []

    number = 1
    parent_bates: str | None = None

    for index in range(documents):
        # A gap, as if documents were culled after Bates assignment.
        if index == 22:
            number += 4

        pages = rng.choice([1, 1, 1, 2, 2, 3, 5])
        beg = f"{prefix}{number:0{width}d}"
        end = f"{prefix}{number + pages - 1:0{width}d}"

        is_attachment = index % 7 == 3 and parent_bates is not None
        beg_attach = parent_bates if is_attachment else ""
        end_attach = end if is_attachment else ""
        if not is_attachment:
            parent_bates = beg

        subject = rng.choice(SUBJECTS)
        custodian = rng.choice(CUSTODIANS)
        author = rng.choice(AUTHORS)
        ext = rng.choice(["msg", "docx", "xlsx", "pdf"])
        date = f"{rng.randint(1, 12):02d}/{rng.randint(1, 28):02d}/202{rng.randint(3, 5)}"
        designation = rng.choice(["", "", "", "CONFIDENTIAL", "ATTORNEYS EYES ONLY"])
        endorsement = designation

        native_rel = f"NATIVES/{beg}.{ext}"
        text_rel = f"TEXT/{beg}.txt"

        lines = [
            f"Subject: {subject}",
            f"From: {author}@{rng.choice(DOMAINS)}",
            f"Date: {date}",
            "",
            rng.choice(COMMON_SNIPPETS),
        ]
        # Only a minority of documents carry the terms that matter.
        if rng.random() < 0.35:
            lines.append(rng.choice(RARE_SNIPPETS))
        body = "\n".join(lines)

        # --- seeded defects -------------------------------------------------
        skip_native = index == 9          # native never copied into the volume
        empty_text = index == 14          # extraction produced nothing
        page_drift = index == 31          # stated page count does not match images
        orphan_family = index == 40       # parent withheld as privileged
        bad_date = index == 47            # date arrived in an unexpected format
        missing_endorsement = index == 52 # designated but not stamped
        # --------------------------------------------------------------------

        if not skip_native:
            (root / native_rel).write_text(body, encoding="utf-8")
        if empty_text:
            (root / text_rel).write_text("", encoding="utf-8")
        else:
            (root / text_rel).write_text(body, encoding="utf-8")

        if orphan_family:
            beg_attach = f"{prefix}9999001"
            end_attach = f"{prefix}9999002"
        if bad_date:
            date = "Sept 4th 2024"
        if missing_endorsement:
            designation = "CONFIDENTIAL"
            endorsement = ""

        stated_pages = pages + 1 if page_drift else pages

        dat_rows.append(
            _row(
                [
                    beg, end, beg_attach, end_attach, custodian, date, author,
                    f"{subject}.{ext}", ext, str(stated_pages), designation,
                    endorsement, native_rel, text_rel,
                ]
            )
        )

        for page in range(pages):
            key = f"{prefix}{number + page:0{width}d}"
            opt_lines.append(
                f"{key},VOL001,IMAGES\\{key}.tif,{'Y' if page == 0 else ''},,,"
                f"{pages if page == 0 else ''}"
            )
            (root / "IMAGES" / f"{key}.tif").write_bytes(b"TIFF placeholder")

        number += pages

    # An image set for a document that was pulled from the DAT late.
    stray = f"{prefix}9990001"
    opt_lines.append(f"{stray},VOL001,IMAGES\\{stray}.tif,Y,,,1")
    (root / "IMAGES" / f"{stray}.tif").write_bytes(b"TIFF placeholder")

    (root / "VOL001.dat").write_text("\r\n".join(dat_rows) + "\r\n", encoding="utf-8")
    (root / "VOL001.opt").write_text("\r\n".join(opt_lines) + "\r\n", encoding="utf-8")
    (root / "terms.txt").write_text(
        "\n".join(
            [
                "# Search terms for the Northbridge matter",
                "rebate",
                "Northbridge",
                "write-down",
                "freight",
                "accrual",
                "legal",
                "audit*",
                "Hensley",
                "unicorn",
                "invoice",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return root


if __name__ == "__main__":  # pragma: no cover
    import sys

    target = build(sys.argv[1] if len(sys.argv) > 1 else "sample/VOL001")
    print(f"Sample production written to {target}")
