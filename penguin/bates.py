"""Bates number handling.

A Bates number is a prefix plus a zero-padded sequence, e.g. ACME-0000123.
Productions are checked for gaps and duplicates because a gap is how a
producing party finds out, late, that documents went missing between
the review platform and the deliverable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

BATES_PATTERN = re.compile(r"^(?P<prefix>.*?)(?P<number>\d+)$")


@dataclass(frozen=True, order=True)
class Bates:
    prefix: str
    number: int
    width: int

    @property
    def text(self) -> str:
        return f"{self.prefix}{self.number:0{self.width}d}"

    def __str__(self) -> str:  # pragma: no cover - convenience only
        return self.text


def parse(value: str) -> Bates | None:
    """Parse a Bates number, or return None if it does not look like one."""
    value = (value or "").strip()
    if not value:
        return None
    match = BATES_PATTERN.match(value)
    if not match:
        return None
    digits = match.group("number")
    return Bates(
        prefix=match.group("prefix"),
        number=int(digits),
        width=len(digits),
    )


@dataclass
class Gap:
    prefix: str
    after: str
    before: str
    missing: int


def find_gaps(values: list[Bates]) -> list[Gap]:
    """Find breaks in an otherwise continuous Bates range.

    Values are grouped by prefix first, because a production can legitimately
    contain more than one prefix.
    """
    by_prefix: dict[str, list[Bates]] = {}
    for bates in values:
        by_prefix.setdefault(bates.prefix, []).append(bates)

    gaps: list[Gap] = []
    for prefix, group in sorted(by_prefix.items()):
        ordered = sorted(set(group))
        for current, following in zip(ordered, ordered[1:]):
            missing = following.number - current.number - 1
            if missing > 0:
                gaps.append(
                    Gap(
                        prefix=prefix,
                        after=current.text,
                        before=following.text,
                        missing=missing,
                    )
                )
    return gaps


def find_duplicates(values: list[Bates]) -> dict[str, int]:
    """Return Bates numbers that appear more than once, with their counts."""
    counts: dict[str, int] = {}
    for bates in values:
        counts[bates.text] = counts.get(bates.text, 0) + 1
    return {text: count for text, count in sorted(counts.items()) if count > 1}


def expand_range(begin: Bates, end: Bates) -> list[str]:
    """List every Bates number from begin to end inclusive."""
    if begin.prefix != end.prefix or end.number < begin.number:
        return []
    width = max(begin.width, end.width)
    return [
        f"{begin.prefix}{number:0{width}d}"
        for number in range(begin.number, end.number + 1)
    ]
