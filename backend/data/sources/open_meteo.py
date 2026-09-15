"""Open-Meteo weather enrichment for crisis events.

Open-Meteo is not an event *source*; it is used to attach current weather
(temperature, wind speed, precipitation) to crisis events as metadata so that
downstream ML can use weather context. Requires no API key.
"""
from __future__ import annotations

import asyncio
import logging
import math
from typing import Any

import httpx

from ..http import fetch_json
from ..schema import CrisisEvent
from .base import BaseSource

logger = logging.getLogger(__name__)

DEFAULT_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


class OpenMeteoSource(BaseSource):
    """Fetches current weather for crisis locations and attaches it to an
    event's ``metadata["weather"]``."""

    name = "open_meteo"
    default_requests_per_second = 5.0

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.api_url = self.config.get("api_url", DEFAULT_FORECAST_URL)

    async def fetch_for_event(self, client: httpx.AsyncClient, event: CrisisEvent) -> dict[str, Any]:
        """Fetch current weather for one event's coordinates. Raises if the event
        has no valid coordinates."""
        lat, lon = event.latitude, event.longitude
        if math.isnan(lat) or math.isnan(lon):
            raise ValueError(f"Event has no coordinates: {event.title!r}")
        params = {
            "latitude": lat,
            "longitude": lon,
            "current_weather": "true",
            "timezone": "UTC",
        }
        payload = await fetch_json(
            client, self.api_url, params=params, rate_limiter=self.rate_limiter,
            retries=self.config.get("retries"),
        )
        return self._payload_to_weather(payload)

    async def enrich_events(
        self,
        client: httpx.AsyncClient,
        events: list[CrisisEvent],
        *,
        max_concurrent: int = 5,
    ) -> list[CrisisEvent]:
        """Attach current-weather metadata to events with coordinates.

        Args:
            client: Shared ``httpx.AsyncClient``.
            events: Crisis events to enrich (mutated in place by setting
                ``metadata["weather"]``).
            max_concurrent: Cap on simultaneous weather requests.

        Returns:
            The same ``events`` list, enriched in place.
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def enrich_one(event: CrisisEvent) -> None:
            if math.isnan(event.latitude) or math.isnan(event.longitude):
                return
            async with semaphore:
                try:
                    weather = await self.fetch_for_event(client, event)
                    event.metadata["weather"] = {**event.metadata.get("weather", {}), **weather}
                except Exception as exc:  # noqa: BLE001 - per-event resilience
                    logger.warning(
                        "Weather enrichment failed for %r: %s", event.title, exc,
                    )
                    event.metadata.setdefault("weather_errors", []).append(str(exc))

        await asyncio.gather(*(enrich_one(event) for event in events))
        return events

    @staticmethod
    def _payload_to_weather(payload: dict[str, Any]) -> dict[str, Any]:
        current = payload.get("current_weather") or payload.get("current") or {}
        temperature = current.get("temperature") or current.get("temperature_2m")
        wind_speed = current.get("windspeed") or current.get("wind_speed_10m")
        weather_code = current.get("weathercode") or current.get("weather_code")
        time_str = current.get("time")
        return {
            "temperature": temperature,
            "wind_speed": wind_speed,
            "precipitation": current.get("precipitation"),
            "weather_code": weather_code,
            "observation_time": time_str,
        }