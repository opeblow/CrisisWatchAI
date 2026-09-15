"""GDACS (Global Disaster Alert and Coordination System) RSS feed parser."""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

import feedparser
import httpx

from ..http import fetch_text
from ..schema import CrisisEvent, UNKNOWN_COORD
from ..utils import parse_datetime, strip_html
from .base import BaseSource, safe_float

logger = logging.getLogger(__name__)

DEFAULT_FEED_URL = "https://www.gdacs.org/xml/rss.xml"

#: GDACS alert levels -> unified severity scale (1-5).
COLOR_SEVERITY = {
    "RED": 5,
    "ORANGE": 4,
    "YELLOW": 3,
    "GREEN": 2,
    "WHITE": 2,
}

#: GDACS hazard category codes -> unified event types.
GDACS_CATEGORY_TO_TYPE = {
    "EQ": "earthquake",
    "TC": "cyclone",     # tropical cyclone
    "HT": "cyclone",     # hurricane / typhoon
    "FL": "flood",
    "DR": "drought",
    "WF": "wildfire",
    "VO": "displacement",  # volcanic eruption (evacuation / displacement)
    "TS": "flood",          # tsunami
}

#: Keyword fallbacks used when the category code is unavailable.
TYPE_KEYWORDS = {
    "earthquake": ["earthquake", "seismic", "tremor", "quake", "aftershock"],
    "cyclone": ["cyclone", "typhoon", "hurricane", "tropical storm", "cyclonic"],
    "flood": ["flash flood", "flood", "river flood"],
    "drought": ["drought", "water shortage", "water scarcity"],
    "wildfire": ["wildfire", "forest fire", "bushfire", "wild fire"],
    "epidemic": ["epidemic", "outbreak", "cholera", "ebola", "disease"],
    "conflict": ["conflict", "armed", "war", "clash"],
    "displacement": ["displaced", "refugee", "evacuation", "displacement"],
}

_COLOR_RE = re.compile(r"\b(RED|ORANGE|YELLOW|GREEN|WHITE)\b", re.IGNORECASE)
_COUNTRY_RE = re.compile(r"\bCountry\s*[:\-]\s*([A-Za-z][A-Za-z\s.']*)", re.IGNORECASE)
_REGION_RE = re.compile(r"\bRegion\s*[:\-]\s*([A-Za-z][A-Za-z\s.']*)", re.IGNORECASE)


def _detect_event_type(text: str) -> Optional[str]:
    """Fallback event-type detection from keywords in a text snippet."""
    lowered = strip_html(text).lower()
    for event_type, keywords in TYPE_KEYWORDS.items():
        for keyword in keywords:
            if keyword.lower() in lowered:
                return event_type
    return None


class GDACSSource(BaseSource):
    """Parses GDACS RSS items into :class:`CrisisEvent` records.

    RSS items carry a hazard ``category`` code (e.g. ``EQ``), a ``georss:point``
    coordinate, a color-coded alert level and a ``pubDate`` timestamp. The
    severity is mapped from the alert color (Red=5 ... Green=2).
    """

    name = "gdacs"
    default_requests_per_second = 0.5

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(config)
        self.feed_url = self.config.get("feed_url", DEFAULT_FEED_URL)

    async def fetch(self, client: httpx.AsyncClient) -> List[CrisisEvent]:
        content = await fetch_text(
            client, self.feed_url, rate_limiter=self.rate_limiter,
            retries=self.config.get("retries"),
        )
        feed = feedparser.parse(content)
        if feed.get("bozo") and not feed.entries:
            logger.warning(
                "GDACS feed failed to parse: %s",
                getattr(feed, "bozo_exception", "unknown error"),
            )

        events: List[CrisisEvent] = []
        for entry in feed.entries:
            event = self._parse_entry(entry)
            if event is not None:
                events.append(event)
        return events

    def _parse_entry(self, entry: Dict[str, Any]) -> Optional[CrisisEvent]:
        title = strip_html(entry.get("title", ""))
        summary = strip_html(entry.get("summary") or entry.get("description") or "")
        combined = f"{title} {summary}"

        if not title and not summary:
            return None

        timestamp = parse_datetime(
            entry.get("published")
            or entry.get("updated")
            or entry.get("published_parsed")
            or entry.get("updated_parsed")
        )
        if timestamp is None:
            logger.warning("GDACS entry without timestamp skipped: %r", title[:80])
            return None

        severity = self._severity_from_color(combined)

        event_type = self._event_type(entry, combined)
        if event_type is None:
            event_type = "displacement"  # GDACS default if entirely unknown
            logger.debug("GDACS category unknown for: %r", title[:80])

        lat, lon = self._coordinates(entry)
        region = self._region(entry, summary)
        country = self._country(summary)

        return CrisisEvent(
            source=self.name,
            event_type=event_type,
            title=title or f"{event_type} alert",
            description=summary,
            severity=severity,
            latitude=lat,
            longitude=lon,
            country=country,
            region=region,
            timestamp=timestamp,
            raw_data=dict(entry),
        )

    @staticmethod
    def _severity_from_color(text: str) -> int:
        match = _COLOR_RE.search(text)
        if match:
            return COLOR_SEVERITY.get(match.group(1).upper(), 3)
        return 3

    @staticmethod
    def _event_type(entry: Dict[str, Any], combined_text: str) -> Optional[str]:
        # 1. Explicit GDACS category code (e.g. <category>EQ</category>).
        for tag in entry.get("tags", []) or []:
            term = str(getattr(tag, "term", "") or "").upper()
            mapped = GDACS_CATEGORY_TO_TYPE.get(term)
            if mapped:
                return mapped
        category = str(entry.get("category", "") or "").upper()
        mapped = GDACS_CATEGORY_TO_TYPE.get(category)
        if mapped:
            return mapped
        # 2. Keyword-based fallback using title + description.
        return _detect_event_type(combined_text)

    @staticmethod
    def _coordinates(entry: Dict[str, Any]):
        """Extract (lat, lon) from GeoRSS fields (georss:point / geo:lat/long)."""
        point = entry.get("geo_point")
        if point is not None and isinstance(point, (tuple, list)) and len(point) >= 2:
            lat, lon = safe_float(point[0]), safe_float(point[1])
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                return lat, lon
        lat, lon = safe_float(entry.get("geo_lat")), safe_float(entry.get("geo_long"))
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            return lat, lon
        return UNKNOWN_COORD, UNKNOWN_COORD

    @staticmethod
    def _region(entry: Dict[str, Any], summary: str) -> str:
        featurename = entry.get("georss_featurename")
        if featurename:
            return strip_html(featurename)
        match = _REGION_RE.search(summary)
        if match:
            return match.group(1).strip()
        match = _COUNTRY_RE.search(summary)
        return match.group(1).strip() if match else ""

    @staticmethod
    def _country(summary: str) -> str:
        match = _COUNTRY_RE.search(summary)
        return match.group(1).strip() if match else ""