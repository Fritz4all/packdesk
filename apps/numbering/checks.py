"""Compare a counter with the documents that actually exist.

Issued numbers come from "sources". The archive of old PDF files is one;
modules add their own (e.g. the invoices table) with `register_source`.
"""

import os
import re
from dataclasses import dataclass, field

from django.conf import settings

_SOURCES = {}


def register_source(key, func):
    """`func(sequence)` returns an iterable of issued counter values for sequence `key`."""
    _SOURCES.setdefault(key, []).append(func)


def archive_numbers(sequence):
    folder = getattr(settings, "DOCUMENT_ARCHIVE_DIR", "")
    if not sequence.archive_regex or not folder or not os.path.isdir(folder):
        return []
    regex = re.compile(sequence.archive_regex)
    numbers = []
    with os.scandir(folder) as entries:
        for entry in entries:
            match = regex.fullmatch(entry.name)
            if match and entry.is_file():
                numbers.append(int(match.group(1)))
    return numbers


def issued_numbers(sequence):
    numbers = set(archive_numbers(sequence))
    for func in _SOURCES.get(sequence.key, []):
        numbers.update(func(sequence))
    return numbers


def ranges(numbers):
    """[1, 2, 3, 7, 9, 10] -> [(1, 3), (7, 7), (9, 10)]"""
    out = []
    for n in sorted(numbers):
        if out and n == out[-1][1] + 1:
            out[-1] = (out[-1][0], n)
        else:
            out.append((n, n))
    return out


def subtract(first, last, notes):
    """Parts of first..last not covered by any explained gap."""
    parts = [(first, last)]
    for note in sorted(notes, key=lambda n: n.first):
        next_parts = []
        for a, b in parts:
            if note.last < a or note.first > b:
                next_parts.append((a, b))
                continue
            if note.first > a:
                next_parts.append((a, note.first - 1))
            if note.last < b:
                next_parts.append((note.last + 1, b))
        parts = next_parts
    return parts


@dataclass
class CheckResult:
    status: str  # ok, empty, behind, ahead, yearly
    count: int = 0
    lowest: int | None = None
    highest: int | None = None
    next_number: int = 1
    gaps: list = field(default_factory=list)  # unexplained (first, last)
    explained: list = field(default_factory=list)  # (first, last, note)
    source_available: bool = True

    @property
    def missing_count(self):
        return sum(last - first + 1 for first, last in self.gaps)

    @property
    def has_problem(self):
        return self.status == "behind" or bool(self.gaps)

    @property
    def suggested_next(self):
        return (self.highest or 0) + 1


def check(sequence):
    numbers = issued_numbers(sequence)
    result = CheckResult(status="ok", next_number=sequence.next_number)
    archive = bool(sequence.archive_regex) and os.path.isdir(getattr(settings, "DOCUMENT_ARCHIVE_DIR", ""))
    result.source_available = archive or bool(_SOURCES.get(sequence.key))
    if sequence.reset_yearly:
        result.status = "yearly"
        return result
    if not numbers:
        result.status = "empty"
        return result

    result.count = len(numbers)
    result.lowest, result.highest = min(numbers), max(numbers)
    notes = list(sequence.gap_notes.all())
    present = ranges(numbers)
    holes = [(end + 1, start - 1) for (_a, end), (start, _b) in zip(present, present[1:])]
    if sequence.next_number <= result.highest:
        result.status = "behind"
    elif sequence.next_number > result.highest + 1:
        result.status = "ahead"
        # Numbers handed out after the highest document that no longer exist.
        holes.append((result.highest + 1, sequence.next_number - 1))
    for first, last in holes:
        open_parts = subtract(first, last, notes)
        result.gaps.extend(open_parts)
        for note in notes:
            if note.first <= last and note.last >= first:
                result.explained.append((max(first, note.first), min(last, note.last), note))
    return result
