"""USGS Earthquake Hazards Program event API parser."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from ..http import fetch_json
from ..schema import UNKNOWN_COORD, CrisisEvent
from ..utils import strip_html
from .base import BaseSource, safe_float

logger = logging.getLogger(__name__)

DEFAULT_API_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query"


def magnitude_to_severity(mag: float) -> int:
    """Map USGS magnitude to the unified 1-5 severity scale (per project spec).

    4.5-5.4 -> 2, 5.5-6.4 -> 3, 6.5-7.4 -> 4, 7.5+ -> 5. Magnitudes below the
    query threshold are mapped to severity 1.
    """
    if mag >= 7.5:
        return 5
    if mag >= 6.5:
        return 4
    if mag >= 5.5:
        return 3
    if mag >= 4.5:
        return 2
    return 1


class USGSSource(BaseSource):
    """Fetches recent earthquakes (>= minmagnitude) from the USGS FDSN Event
    web service, returning them as normalized ``earthquake`` events.
    """

    name = "usgs"
    default_requests_per_second = 2.0

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.api_url = self.config.get("api_url", DEFAULT_API_URL)
        self.min_magnitude = float(self.config.get("minmagnitude", 4.5))
        self.days = int(self.config.get("days", 7))

    async def fetch(self, client: httpx.AsyncClient) -> list[CrisisEvent]:
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=self.days)
        params = {
            "format": "geojson",
            "starttime": start.strftime("%Y-%m-%d"),
            "minmagnitude": str(self.min_magnitude),
        }
        payload = await fetch_json(
            client, self.api_url, params=params, rate_limiter=self.rate_limiter,
            retries=self.config.get("retries"),
        )
        features = (payload or {}).get("features", []) or []
        events: list[CrisisEvent] = []
        for feature in features:
            event = self._parse_feature(feature)
            if event is not None:
                events.append(event)
        return events

    def _parse_feature(self, feature: dict[str, Any]) -> CrisisEvent | None:
        props = feature.get("properties") or {}
        geometry = feature.get("geometry") or {}

        mag = safe_float(props.get("mag"))
        if mag == float("nan"):
            return None

        coords = geometry.get("coordinates") or []
        lon = safe_float(coords[0]) if len(coords) >= 2 else UNKNOWN_COORD
        lat = safe_float(coords[1]) if len(coords) >= 2 else UNKNOWN_COORD
        depth_km = safe_float(coords[2]) if len(coords) >= 3 else float("nan")

        place = strip_html(props.get("place") or feature.get("id") or "Earthquake")
        ts_ms = props.get("time")
        timestamp = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc) if ts_ms else None
        if timestamp is None:
            return None

        severity = magnitude_to_severity(mag)
        # A tsunami alert or Red alert bumps severity (capped at 5).
        if props.get("tsunami") in (1, 2) or str(props.get("alert", "")).upper() == "RED":
            severity = min(5, severity + 1)

        region = place
        # Try to pull a country/state hint from the trailing segment of the place name.
        country = ""
        place_parts = [p.strip() for p in place.split(",") if p.strip()]
        if len(place_parts) >= 2:
            country = place_parts[-1]

        metadata = {
            key: props.get(key) for key in (
                "mag", "magType", "place", "time", "tsunami", "felt",
                "cdi", "mmi", "sig", "alert", "status", "url", "type",
            ) if key in props
        }
        metadata["depth_km"] = depth_km
        metadata["usgs_id"] = feature.get("id")

        description = (
            f"Magnitude {mag:.1f} earthquake (depth {depth_km:.1f} km). "
            f"Place: {place}."
        )

        return CrisisEvent(
            source=self.name,
            event_type="earthquake",
            title=place,
            description=description,
            severity=severity,
            latitude=lat,
            longitude=lon,
            country=country,
            region=region,
            timestamp=timestamp,
            casualties=None,  # felt reports stored in metadata["felt"], not confirmed casualties
            affected=None,
            raw_data=dict(feature),
            metadata=metadata,
        )