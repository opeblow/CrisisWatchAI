"""NASA FIRMS (Fire Information for Resource Management System) active fire data.

Supports two upstream modes:

* **Area CSV API** — ``https://firms.modaps.eosdis.nasa.gov/api/area/csv``
  (requires a ``MAP_KEY``).
* **Open 24h CSV endpoint** — the publicly accessible daily global dump, e.g.
  ``https://firms.modaps.eosdis.nasa.gov/active_fire/viirs/text/VIIRS_SNPP_NRT_Global_24h.csv``.

Both return CSV with the same FIRMS row layout (latitude, longitude, frp,
confidence, acq_date, acq_time, satellite, ...).
"""
from __future__ import annotations

import csv
import io
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx

from ..http import fetch_text
from ..schema import CrisisEvent, UNKNOWN_COORD
from .base import BaseSource, safe_float

logger = logging.getLogger(__name__)

AREA_API_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
#: Public (no-key) global daily hot-spot CSV endpoints.
OPEN_CSV_URLS = {
    "VIIRS_SNPP_NRT": "https://firms.modaps.eosdis.nasa.gov/active_fire/viirs/text/VIIRS_SNPP_NRT_Global_24h.csv",
    "VIIRS_NOAA20_NRT": "https://firms.modaps.eosdis.nasa.gov/active_fire/viirs/text/VIIRS_NOAA20_NRT_Global_24h.csv",
    "MODIS_NRT": "https://firms.modaps.eosdis.nasa.gov/active_fire/c6/text/MODIS_C6_Global_24h.csv",
}


def frp_to_severity(frp: float) -> int:
    """Map Fire Radiative Power (MW) to the unified 1-5 severity scale."""
    if frp >= 600:
        return 5
    if frp >= 300:
        return 4
    if frp >= 150:
        return 3
    if frp >= 50:
        return 2
    return 1


def _parse_confidence(value: Any) -> Optional[int]:
    """Normalize a FIRMS confidence field to a 0-100 integer.

    Area API rows use categories (``low``/``nominal``/``high``); the open CSV
    endpoints use the single-letter compact codes (``l``/``n``/``h``); MODIS
    C6 rows sometimes carry a numeric percentage.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return max(0, min(100, int(float(value))))
        except (TypeError, ValueError):
            return None
    text = str(value).strip().lower()
    mapping = {"h": 100, "high": 100, "n": 50, "nominal": 50, "l": 0, "low": 0}
    if text in mapping:
        return mapping[text]
    try:
        return max(0, min(100, int(float(text))))
    except (TypeError, ValueError):
        return None


class NASAFIRMSSource(BaseSource):
    """Fetches and filters recent active-fire detections from NASA FIRMS."""

    name = "nasa_firms"
    default_requests_per_second = 0.5

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(config)
        self.api_key = self.config.get("api_key")
        self.satellite = self.config.get("satellite", "VIIRS_SNPP_NRT")
        self.days = int(self.config.get("days", 1))  # API supports up to 7
        #: Minimum confidence percent to keep (0-100). Default keeps only high confidence.
        self.min_confidence = int(self.config.get("min_confidence", 80))

    @property
    def _open_csv_url(self) -> str:
        return OPEN_CSV_URLS.get(self.satellite, OPEN_CSV_URLS["VIIRS_SNPP_NRT"])

    async def _fetch_csv(self, client: httpx.AsyncClient) -> str:
        """Fetch the appropriate CSV payload (area API when key present, open
        CSV endpoint otherwise)."""
        if self.api_key:
            end = datetime.now(timezone.utc)
            start = end - timedelta(days=max(1, self.days))
            url = (
                f"{AREA_API_URL}/{self.api_key}/{self.satellite}/"
                f"world/{self.days}/{start.strftime('%Y-%m-%d')}"
            )
            logger.info("FIRMS: using area API for %s (last %d days)", self.satellite, self.days)
        else:
            url = self._open_csv_url
            logger.info("FIRMS: using open CSV endpoint %s", url)
        return await fetch_text(
            client, url, rate_limiter=self.rate_limiter,
            retries=self.config.get("retries"),
        )

    async def fetch(self, client: httpx.AsyncClient) -> List[CrisisEvent]:
        content = await self._fetch_csv(client)
        rows = list(csv.DictReader(io.StringIO(content)))
        if not rows:
            logger.warning("FIRMS returned an empty CSV payload")
            return []

        events: List[CrisisEvent] = []
        for row in rows:
            event = self._parse_row(row)
            if event is not None:
                events.append(event)
        return events

    def _parse_row(self, row: Dict[str, str]) -> Optional[CrisisEvent]:
        lat = safe_float(row.get("latitude"))
        lon = safe_float(row.get("longitude"))
        if lat == float("nan") or lon == float("nan"):
            return None

        confidence = _parse_confidence(row.get("confidence"))
        if confidence is not None and confidence < self.min_confidence:
            return None  # drop low-confidence detections

        frp = safe_float(row.get("frp"))
        severity = frp_to_severity(frp) if frp == frp else 1

        timestamp = self._acquisition_timestamp(row.get("acq_date"), row.get("acq_time"))
        if timestamp is None:
            return None

        satellite = row.get("satellite") or self.satellite
        instrument = row.get("instrument") or "VIIRS"
        title = f"Active fire ({satellite}/{instrument}) near ({lat:.2f}, {lon:.2f})"
        description = (
            f"Fire detection with FRP {frp:.1f} MW and confidence "
            f"{confidence if confidence is not None else 'unknown'} on {timestamp:%Y-%m-%d}."
        )

        metadata = {
            k: row.get(k) for k in ("bright_ti4", "bright_ti5", "scan", "track",
                                    "daynight", "version", "acq_date", "acq_time")
        }
        metadata["confidence"] = confidence
        metadata["frp"] = frp

        return CrisisEvent(
            source=self.name,
            event_type="wildfire",
            title=title,
            description=description,
            severity=severity,
            latitude=lat,
            longitude=lon,
            country="",
            region="",
            timestamp=timestamp,
            affected=1 if confidence is not None and confidence >= 80 else None,
            raw_data=dict(row),
            metadata=metadata,
        )

    @staticmethod
    def _acquisition_timestamp(acq_date: Optional[str], acq_time: Optional[str]) -> Optional[datetime]:
        """Combine FIRMS ``acq_date`` (YYYY-MM-DD) and ``acq_time`` (HHMM, UTC)."""
        if not acq_date:
            return None
        try:
            date_part = datetime.strptime(acq_date[:10], "%Y-%m-%d")
        except (ValueError, TypeError):
            return None
        hour_min = acq_time or "0000"
        try:
            hour = int(hour_min[:2])
            minute = int(hour_min[2:4])
        except (ValueError, TypeError):
            hour = minute = 0
        return date_part.replace(hour=hour, minute=minute, tzinfo=timezone.utc)