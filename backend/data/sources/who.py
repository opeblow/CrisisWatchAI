"""WHO Disease Outbreak News (DON) RSS feed parser.

The WHO publishes Disease Outbreak News entries as an RSS feed. Because the
feed entries only carry a disease name, a short HTML description and a publish
date (no calibrated severity), severity is estimated from reported case/death
figures parsed out of the description text.
"""
from __future__ import annotations

import logging
import re
from typing import Any

import feedparser
import httpx

from ..http import fetch_text
from ..schema import UNKNOWN_COORD, CrisisEvent
from ..utils import parse_datetime, strip_html
from .base import BaseSource

logger = logging.getLogger(__name__)

DEFAULT_FEED_URL = "https://www.who.int/feeds/entity/don/en/rss.xml"

#: Description patterns that surface case and death counts.
_CASE_PATTERN = re.compile(
    r"(?P<count>[\d,]+(?!\s*outbreak))(?:\s*[-\u2013\u2014]|(?:\s+confirmed)?\s+)"
    r"(?:cases?|infections?|tested\s+positive)",
    re.IGNORECASE,
)
_DEATH_PATTERN = re.compile(r"(?P<count>[\d,]+)\s+(?:reported\s+)?deaths?", re.IGNORECASE)
#: Leading disease name / dash-separated country forms ("Dengue - Iran" or
#: "Heatstroke: Iran" style titles).
_TITLE_SPLIT = re.compile(r"[\s\u00b7|]+?[-:\u2013\u2014;]\s+")


def _count_from(count: str | None) -> int | None:
    return int(count.replace(",", "")) if count else None


def estimate_severity(cases: int | None, deaths: int | None) -> int:
    """Heuristic severity from reported case/death counts."""
    if deaths is not None and deaths >= 100:
        return 5
    if deaths is not None and deaths >= 10:
        return 4
    if cases is not None and cases >= 1000:
        return 4
    if cases is not None and cases >= 100:
        return 3
    return 3 if cases is None else 2


class WHOSource(BaseSource):
    """Fetches and parses WHO Disease Outbreak News into ``epidemic`` events."""

    name = "who"
    default_requests_per_second = 0.5

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.feed_url = self.config.get("feed_url", DEFAULT_FEED_URL)

    async def fetch(self, client: httpx.AsyncClient) -> list[CrisisEvent]:
        content = await fetch_text(
            client, self.feed_url, rate_limiter=self.rate_limiter,
            retries=self.config.get("retries"),
        )
        feed = feedparser.parse(content)
        if feed.get("bozo") and not feed.entries:
            logger.warning("WHO feed failed to parse: %s", getattr(feed, "bozo_exception", "unknown"))

        events: list[CrisisEvent] = []
        for entry in feed.entries:
            event = self._parse_entry(entry)
            if event is not None:
                events.append(event)
        return events

    def _parse_entry(self, entry: dict[str, Any]) -> CrisisEvent | None:
        title = strip_html(entry.get("title", ""))
        description = strip_html(entry.get("summary") or entry.get("description") or "")
        if not title and not description:
            return None

        timestamp = parse_datetime(entry.get("published") or entry.get("updated"))
        if timestamp is None:
            return None

        disease, country = self._parse_title(title)

        cases = self._extract_cases(description) or self._extract_cases(title)
        deaths = _count_from(self._first_match(description, _DEATH_PATTERN)) or _count_from(
            self._first_match(title, _DEATH_PATTERN)
        )
        severity = estimate_severity(cases, deaths)

        metadata = {
            "disease": disease,
            "confirmed_cases": cases,
            "deaths": deaths,
            "url": entry.get("link"),
            "guid": entry.get("id"),
        }

        return CrisisEvent(
            source=self.name,
            event_type="epidemic",
            title=title or f"{disease} outbreak",
            description=description or f"{disease} reported by WHO.",
            severity=severity,
            latitude=UNKNOWN_COORD,
            longitude=UNKNOWN_COORD,
            country=country,
            region="",
            timestamp=timestamp,
            casualties=deaths,
            affected=cases,
            raw_data=dict(entry),
            metadata=metadata,
        )

    @staticmethod
    def _parse_title(title: str):
        """Split a WHO title like ``Dengue - Brazil`` or ``X Disease: Region``
        into a disease name and a country/region guess."""
        parts = _TITLE_SPLIT.split(title, maxsplit=1)
        disease = strip_html(parts[0]) if parts and parts[0] else title
        guess = strip_html(parts[1]) if len(parts) > 1 else ""
        if not disease:
            disease = "Outbreak"
        # A WHO title often begins with the disease name; country is the tail.
        return disease, guess

    @staticmethod
    def _extract_cases(text: str) -> int | None:
        for match in _CASE_PATTERN.finditer(text):
            cases = _count_from(match.groupdict().get("count"))
            if cases is not None:
                return cases
        return None

    @staticmethod
    def _first_match(text: str, pattern: re.Pattern) -> str | None:
        match = pattern.search(text)
        if not match:
            return None
        group = (match.groupdict() or {}).get("count")
        return group or (match.group(1) if match.groups() else None)