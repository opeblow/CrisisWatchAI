"""ACLED (Armed Conflict Location & Event Data Project) conflict data source.

Hits the ACLED public/registered API (``/v1/events``) and maps its rich event
taxonomy onto the unified ``conflict`` event type. Severity is driven by the
ACLED event subtype and the reported fatality count.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from ..http import fetch_json
from ..schema import UNKNOWN_COORD, CrisisEvent
from ..utils import strip_html
from .base import BaseSource, safe_float, safe_int

logger = logging.getLogger(__name__)

DEFAULT_API_URL = "https://api.acleddata.org/v1/events"

#: ACLED event types -> baseline severity.
EVENT_TYPE_SEVERITY = {
    "Violence against civilians": 5,
    "Explosions/Remote violence": 5,
    "Battles": 4,
    "Riots": 3,
    "Protests": 3,
    "Strategic developments": 2,
    "Other": 2,
}
DEFAULT_EVENT_SEVERITY = 3


class ACLEDSource(BaseSource):
    """Fetches recent conflict events from the ACLED API.

    The public API requires ``email`` + ``key`` query parameters. The sample
    credentials ``guest@example.com``/``guest`` are used by default; set
    ``ACLED_EMAIL``/``ACLED_KEY`` environment variables or pass ``email``/``key``
    through config for a registered account.
    """

    name = "acled"
    default_requests_per_second = 0.5

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.api_url = self.config.get("api_url", DEFAULT_API_URL)
        self.email = self.config.get("email")
        self.key = self.config.get("key")
        self.limit = int(self.config.get("limit", 100))
        self.days = int(self.config.get("days", 7))

    async def fetch(self, client: httpx.AsyncClient) -> list[CrisisEvent]:
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=self.days)
        params = {
            "email": self.email,
            "key": self.key,
            "limit": str(self.limit),
            "event_date": ",".join([start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")]),
            # ACLED commonly requires an explicit where-clause for date filters.
            "event_date_where": "BETWEEN",
        }
        # Drop entries whose values are None so we don't send "None" params.
        params = {k: v for k, v in params.items() if v is not None}

        payload = await fetch_json(
            client, self.api_url, params=params, rate_limiter=self.rate_limiter,
            retries=self.config.get("retries"),
        )
        data = (payload or {}).get("data", []) or []
        events: list[CrisisEvent] = []
        for record in data:
            event = self._parse_record(record)
            if event is not None:
                events.append(event)
        return events

    def _parse_record(self, record: dict[str, Any]) -> CrisisEvent | None:
        acled_type = strip_html(record.get("event_type") or "Other")
        fatalities = safe_int(record.get("fatalities"))

        lat = safe_float(record.get("latitude"))
        lon = safe_float(record.get("longitude"))

        timestamp = self._parse_timestamp(record)
        if timestamp is None:
            return None

        severity = EVENT_TYPE_SEVERITY.get(acled_type, DEFAULT_EVENT_SEVERITY)
        # Escalate severity based on the reported death toll (capped at 5).
        if fatalities:
            if fatalities >= 100:
                severity = 5
            elif fatalities >= 10:
                severity = max(severity, 4)

        country = strip_html(record.get("country") or "")
        location = strip_html(record.get("location") or "")
        admin1 = strip_html(record.get("admin1") or "")
        actors = [
            case for a in (record.get("actor1"), record.get("actor2")) if (case := strip_html(a))
        ]
        title = f"{acled_type} - {location or admin1 or country or 'Unknown location'}"
        description = (
            f"{acled_type} in {location or admin1 or country or 'unknown'} with "
            f"{fatalities if fatalities is not None else 'unknown'} fatalities. "
            f"Actors: {', '.join(actors) if actors else 'unknown'}."
        )

        metadata = {
            "event_id_cnty": record.get("event_id_cnty"),
            "event_type": acled_type,
            "sub_event_type": strip_html(record.get("sub_event_type") or ""),
            "fatalities": fatalities,
            "year": record.get("year"),
            "admin1": admin1,
            "admin2": strip_html(record.get("admin2") or ""),
            "location": location,
            "source": strip_html(record.get("source") or ""),
            "notes": strip_html(record.get("notes") or "")[:200],
            "url": record.get("url") or f"https://acleddata.com/dashboard/#/{record.get('event_id_cnty', '')}",
        }

        return CrisisEvent(
            source=self.name,
            event_type="conflict",
            title=title,
            description=description,
            severity=severity,
            latitude=lat if -90 <= lat <= 90 else UNKNOWN_COORD,
            longitude=lon if -180 <= lon <= 180 else UNKNOWN_COORD,
            country=country,
            region=admin1,
            timestamp=timestamp,
            casualties=fatalities,
            displaced=None,
            affected=None,
            raw_data=dict(record),
            metadata=metadata,
        )

    @staticmethod
    def _parse_timestamp(record: dict[str, Any]) -> datetime | None:
        event_date = record.get("event_date")  # YYYY-MM-DD
        if not event_date:
            return None
        try:
            date_obj = datetime.strptime(event_date[:10], "%Y-%m-%d")
        except (ValueError, TypeError):
            return None
        return date_obj.replace(tzinfo=timezone.utc)