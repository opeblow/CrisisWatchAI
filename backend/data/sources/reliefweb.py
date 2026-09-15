"""ReliefWeb (UN OCHA) reports API source.

ReliefWeb publishes humanitarian situation reports and crisis documents.
Event type and severity are inferred from the disaster-type metadata and by
scanning titles/bodies for crisis-type keywords.
"""
from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from ..http import fetch_json
from ..schema import UNKNOWN_COORD, CrisisEvent
from ..utils import parse_datetime, strip_html
from .base import BaseSource

logger = logging.getLogger(__name__)

DEFAULT_API_URL = "https://api.reliefweb.int/v1/reports"

#: Keyword groups used to classify the implied crisis type.
TYPE_KEYWORDS = {
    "earthquake": ["earthquake", "seismic", "quake", "aftershock", "tremor"],
    "flood": ["flood", "flooding", "flash flood", "riverine", "monsoon"],
    "cyclone": ["cyclone", "typhoon", "hurricane", "tropical storm", "cyclonic"],
    "drought": ["drought", "dry spell", "water scarcity", "famine"],
    "wildfire": ["wildfire", "forest fire", "bushfire", "wild fire", "burn"],
    "epidemic": ["epidemic", "outbreak", "cholera", "ebola", "measles", "dengue",
                 "polio", "zika", "pandemic", "disease", "covid"],
    "conflict": ["conflict", "armed conflict", "war", "violence", "fighting",
                 "airstrike", "insurgency", "clash"],
    "displacement": ["displaced", "displacement", "refugee", "internally displaced",
                     "idp", "evacuation", "forced to flee"],
}

#: Baseline severity per disaster-type name as reported by ReliefWeb.
DISASTER_SEVERITY = {
    "Earthquakes": 4,
    "Tropical Cyclones": 4,
    "Tsunami": 4,
    "Floods": 3,
    "Land Slides": 3,
    "Epidemics": 4,
    "Drought": 3,
    "Wild Fires": 3,
    "Volcanic Eruptions": 3,
    "Heat Wave": 2,
    "Cold Wave": 2,
    "Storm": 3,
    "Refugee Crisis": 3,
    "Armed Conflict": 4,
}
DEFAULT_DISASTER_SEVERITY = 3


def _lower_hits(text: str, keywords):
    lowered = strip_html(text).lower()
    return [k for k in keywords if k in lowered]


class ReliefWebSource(BaseSource):
    """Fetches recent ReliefWeb reports, converting each into a crisis event."""

    name = "reliefweb"
    default_requests_per_second = 0.5

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.api_url = self.config.get("api_url", DEFAULT_API_URL)
        self.limit = int(self.config.get("limit", 50))

    async def fetch(self, client: httpx.AsyncClient) -> list[CrisisEvent]:
        params = {
            "appname": "crisiswatch",
            "limit": str(self.limit),
            "sort": "date:desc",
        }
        payload = await fetch_json(
            client, self.api_url, params=params, rate_limiter=self.rate_limiter,
            retries=self.config.get("retries"),
        )
        data = (payload or {}).get("data", []) or []
        events: list[CrisisEvent] = []
        for item in data:
            event = self._parse_report(item)
            if event is not None:
                events.append(event)
        return events

    def _parse_report(self, item: dict[str, Any]) -> CrisisEvent | None:
        fields = item.get("fields") or {}
        title = strip_html(fields.get("title") or item.get("href") or "ReliefWeb report")
        if not title:
            title = "ReliefWeb report"

        body = strip_html(fields.get("body-html") or fields.get("body") or "")
        combined = f"{title} {body}"

        countries = fields.get("country") or fields.get("countries") or []
        if isinstance(countries, dict):
            countries = [countries]
        country_list = []
        for c in countries:
            if isinstance(c, dict) and c.get("name"):
                country_list.append(str(c["name"]))
        country = "; ".join(sorted(set(country_list))) if country_list else ""

        disaster_types = fields.get("disaster_type") or fields.get("disastertype") or []
        if isinstance(disaster_types, dict):
            disaster_types = [disaster_types]
        disaster_names = [
            d.get("name", "") for d in disaster_types if isinstance(d, dict)
        ]

        timestamp = parse_datetime(
            (fields.get("date") or {}).get("created") or item.get("created")
        )
        if timestamp is None:
            return None

        event_type = self._detect_event_type(combined)
        severity = self._disaster_severity(disaster_names, combined, event_type)

        source_names = [
            s.get("shortname") or s.get("name", "")
            for s in fields.get("source") or [] if isinstance(s, dict)
        ]

        metadata = {
            "reliefweb_id": item.get("id"),
            "url": item.get("href") or fields.get("url"),
            "sources": [s for s in source_names if s],
            "disaster_types": disaster_names,
            "language": (item.get("fields") or {}).get("language"),
        }

        return CrisisEvent(
            source=self.name,
            event_type=event_type or "displacement",  # fallback classification
            title=title or "ReliefWeb report",
            description=body or title,
            severity=severity,
            latitude=UNKNOWN_COORD,
            longitude=UNKNOWN_COORD,
            country=country,
            region="",
            timestamp=timestamp,
            raw_data=dict(item),
            metadata=metadata,
        )

    @staticmethod
    def _detect_event_type(text: str) -> str | None:
        """Classify the event type from combined title+body text."""
        best_type, best_score = None, 0
        for event_type, keywords in TYPE_KEYWORDS.items():
            score = len(_lower_hits(text, keywords))
            if score > best_score:
                best_type, best_score = event_type, score
        return best_type

    @staticmethod
    def _disaster_severity(disaster_names: list[str], text: str, event_type: str | None) -> int:
        severity = DEFAULT_DISASTER_SEVERITY
        for name in disaster_names:
            severity = max(severity, DISASTER_SEVERITY.get(name, DEFAULT_DISASTER_SEVERITY))
        # Bump for escalation language in the body.
        if re.search(r"\b(emergency|critical|severe|catastrophic)\b", text, re.I):
            severity = min(5, severity + 1)
        return severity