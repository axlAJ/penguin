"""Search term hit reporting.

Given a term list and the extracted text of a production, report how many
documents each term hits and how many of those hits are unique to that term.
Unique hits are the number that matters in a negotiation: a term that only
finds documents other terms already found is not earning its place on
the list, and a term that hits a third of the corpus is not a term, it
is a complaint about the term list.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .loadfile import DatFile


@dataclass
class TermHit:
    term: str
    documents: int
    unique: int
    pct_of_corpus: float
    note: str = ""


def compile_term(term: str) -> re.Pattern[str]:
    r"""Turn a search term into a regex.

    Supports the wildcards analysts actually type: ``*`` for any run of
    characters and ``?`` for one. Quoted phrases match as phrases.
    Everything else is escaped, so a term like ``profit & loss`` is safe.
    """
    term = term.strip().strip('"')
    pattern = "".join(
        ".*" if char == "*" else "." if char == "?" else re.escape(char)
        for char in term
    )
    # \b does not fire next to a wildcard, so only anchor where it makes sense.
    prefix = r"\b" if term[:1].isalnum() else ""
    suffix = r"\b" if term[-1:].isalnum() else ""
    return re.compile(prefix + pattern + suffix, re.IGNORECASE)


def load_terms(path: str | Path) -> list[str]:
    """Read a term list; one term per line, ``#`` starts a comment."""
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return [
        line.strip()
        for line in lines
        if line.strip() and not line.strip().startswith("#")
    ]


def run(dat: DatFile, root: Path, terms: list[str]) -> list[TermHit]:
    """Score every term against the production's extracted text."""
    patterns = {term: compile_term(term) for term in terms}
    hits: dict[str, set[str]] = {term: set() for term in terms}
    searched = 0

    for record in dat.records:
        link = record.get("TextLink")
        if not link:
            continue
        target = root / link.replace("\\", "/").lstrip("/")
        if not target.exists():
            continue
        try:
            text = target.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        searched += 1
        key = record.get("BegDoc") or f"row {record.row}"
        for term, pattern in patterns.items():
            if pattern.search(text):
                hits[term].add(key)

    results: list[TermHit] = []
    for term in terms:
        documents = hits[term]
        others: set[str] = set()
        for other_term, other_hits in hits.items():
            if other_term != term:
                others |= other_hits
        unique = len(documents - others)
        pct = (len(documents) / searched * 100) if searched else 0.0

        note = ""
        if not documents:
            note = "No hits. Confirm the term is spelled as it appears in the data."
        elif pct >= 50:
            note = "Hits over half the corpus. Likely too broad to be useful."
        elif unique == 0 and len(documents) > 0:
            note = "Every hit is also caught by another term."

        results.append(
            TermHit(
                term=term,
                documents=len(documents),
                unique=unique,
                pct_of_corpus=round(pct, 1),
                note=note,
            )
        )

    results.sort(key=lambda hit: (-hit.documents, hit.term))
    return results
