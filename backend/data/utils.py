"""Small pure helpers shared across the ingestion components."""
from __future__ import annotations

import html
import re
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(text: Optional[str]) -> str:
    """Remove HTML/XML tags and entities, collapsing whitespace."""
    if not text:
        return ""
    text = html.unescape(str(text))
    text = _HTML_TAG_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_datetime(value: object) -> Optional[datetime]:
    """Parse a datetime from RFC-2822 strings, ISO-8601 strings or datetime
    objects, always normalizing to an aware UTC timestamp.

    Returns ``None`` when the value cannot be parsed.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, date):
        dt = datetime(value.year, value.month, value.day)
    else:
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = parsedate_to_datetime(text)
        except (TypeError, ValueError, OverflowError):
            try:
                dt = datetime.fromisoformat(text)
            except ValueError:
                return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def first_int(text: object, default: Optional[int] = None) -> Optional[int]:
    """Return the first integer found in free text (e.g. ``"1 234 cases"``)."""
    if text is None:
        return default
    match = re.search(r"-?\d[\d,.]*", str(text))
    if not match:
        return default
    cleaned = match.group().replace(",", "")
    try:
        return int(float(cleaned))
    except ValueError:
        return default