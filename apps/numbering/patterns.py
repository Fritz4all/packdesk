"""Number patterns such as ``F{year}-{nr:5}`` or ``WS{nr}{letters:2}``.

Tokens:
    {nr}         the counter
    {nr:5}       the counter, padded with zeros to 5 digits
    {year}       four-digit year, {yy} two-digit year, {month} two-digit month
    {letters:2}  random capital letters (as in the previous webshop's quote numbers)
    {block:4}    a letter plus 4 digits that counts on: A0000..A9999, B0000, ...
                 (as in the previous webshop's licence numbers, e.g. {yy}{block:4} = 26A0001);
                 use instead of {nr}
"""

import random
import re
import string

TOKEN = re.compile(r"\{(nr|block|year|yy|month|letters)(?::(\d+))?\}")


class PatternError(ValueError):
    pass


def validate(pattern):
    tokens = [m.group(1) for m in TOKEN.finditer(pattern)]
    if tokens.count("nr") + tokens.count("block") != 1:
        raise PatternError("The pattern must contain {nr} or {block:N} exactly once.")
    leftover = TOKEN.sub("", pattern)
    if "{" in leftover or "}" in leftover:
        raise PatternError("Unknown token in pattern.")


def render(pattern, number, when, rng=random):
    def replace(match):
        token, width = match.group(1), match.group(2)
        if token == "nr":
            return str(number).zfill(int(width)) if width else str(number)
        if token == "block":
            size = 10 ** int(width or 4)
            return chr(ord("A") + number // size) + str(number % size).zfill(int(width or 4))
        if token == "year":
            return f"{when.year:04d}"
        if token == "yy":
            return f"{when.year % 100:02d}"
        if token == "month":
            return f"{when.month:02d}"
        return "".join(rng.choice(string.ascii_uppercase) for _ in range(int(width or 1)))

    return TOKEN.sub(replace, pattern)


def number_from(pattern, value):
    """Read the counter back from a formatted number, or None if it does not match."""
    parts, last = [], 0
    for m in TOKEN.finditer(pattern):
        parts.append(re.escape(pattern[last:m.start()]))
        token, width = m.group(1), m.group(2)
        if token == "nr":
            parts.append(r"(?P<nr>\d+)")
        elif token == "block":
            parts.append(r"(?P<letter>[A-Z])(?P<block>\d{%s})" % (width or 4))
        elif token == "year":
            parts.append(r"\d{4}")
        elif token in ("yy", "month"):
            parts.append(r"\d{2}")
        else:
            parts.append(r"[A-Z]{%s}" % (width or 1))
        last = m.end()
    parts.append(re.escape(pattern[last:]))
    match = re.fullmatch("".join(parts), value)
    if not match:
        return None
    if "block" in match.groupdict() and match.group("block") is not None:
        size = 10 ** len(match.group("block"))
        return (ord(match.group("letter")) - ord("A")) * size + int(match.group("block"))
    return int(match.group("nr"))
