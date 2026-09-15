"""CrisisWatch AI — data ingestion orchestrator.

The :class:`DataIngestionPipeline` concurrently fetches from every configured
event source (GDACS, USGS, NASA FIRMS, ReliefWeb, WHO, ACLED), applies
preprocessing (cleaning, imputation, deduplication, feature engineering) and
aggregates the results into unified :class:`CrisisEvent` objects.

Design principles:

* **Concurrency** — sources run in parallel with ``asyncio`` over one shared
  ``httpx.AsyncClient``.
* **Per-source resilience** — a failing source is logged and skipped without
  aborting the rest of the pipeline.
* **Rate limiting** — each source owns an ``http.RateLimiter`` whose throughput
  is configured per-source.

Usage::

    from backend.data.ingestion import DataIngestionPipeline

    pipeline = DataIngestionPipeline()
    events = await pipeline.run_all()
    df = pipeline.preprocess(events)
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx
import pandas as pd

from .http import DEFAULT_HEADERS
from .preprocessing import preprocess_pipeline
from .schema import CrisisEvent  # re-exported for convenience
from .sources import (
    ACLEDSource,
    GDACSSource,
    NASAFIRMSSource,
    OpenMeteoSource,
    ReliefWebSource,
    USGSSource,
    WHOSource,
)

logger = logging.getLogger(__name__)

#: Default per-source request rate (requests/second).
DEFAULT_RATES = {
    "gdacs": 0.5,
    "usgs": 2.0,
    "nasa_firms": 0.5,
    "reliefweb": 0.5,
    "who": 0.5,
    "acled": 0.5,
    "open_meteo": 5.0,
}

#: Default configuration merged with any user-provided overrides.
DEFAULT_CONFIG: dict[str, Any] = {
    "timeout": 30.0,
    "retries": 3,
    "requests_per_second": DEFAULT_RATES,
    "sources": {
        "gdacs": {},
        "usgs": {"minmagnitude": 4.5, "days": 7},
        "nasa_firms": {"days": 1, "min_confidence": 80, "satellite": "VIIRS_SNPP_NRT"},
        "reliefweb": {"limit": 50},
        "who": {},
        "acled": {"days": 7, "limit": 100},
    },
    "enrich_weather": False,
    "max_weather_concurrency": 5,
}


def _merge_dict(base: dict[str, Any], override: dict[str, Any] | None) -> dict[str, Any]:
    """Deep-merge ``override`` into ``base`` (both left intact)."""
    merged = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dict(merged[key], value)
        else:
            merged[key] = value
    return merged


@dataclass
class IngestionResult:
    """Output of a full ingestion run."""

    events: list[CrisisEvent] = field(default_factory=list)
    source_errors: dict[str, Exception] = field(default_factory=dict)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def duration_seconds(self) -> float:
        return (self.finished_at - self.started_at).total_seconds()


class DataIngestionPipeline:
    """Orchestrates concurrent fetching, preprocessing and aggregation of
    crisis events from all configured providers."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = _merge_dict(DEFAULT_CONFIG, config)

        rates = self.config["requests_per_second"]

        def source_config(name: str) -> dict[str, Any]:
            cfg = dict(self.config["sources"].get(name, {}))
            cfg.setdefault("requests_per_second", rates.get(name, 0.5))
            cfg.setdefault("retries", self.config["retries"])
            return cfg

        self.sources: dict[str, Any] = {
            "gdacs": GDACSSource(source_config("gdacs")),
            "usgs": USGSSource(source_config("usgs")),
            "nasa_firms": NASAFIRMSSource(source_config("nasa_firms")),
            "reliefweb": ReliefWebSource(source_config("reliefweb")),
            "who": WHOSource(source_config("who")),
            "acled": ACLEDSource(source_config("acled")),
        }
        self.open_meteo = OpenMeteoSource(
            {"requests_per_second": rates.get("open_meteo", 5.0),
             "retries": self.config["retries"]}
        )

    # -- public API ----------------------------------------------------------

    async def run_all(
        self,
        *,
        prefetch_weather: bool | None = None,
    ) -> list[CrisisEvent]:
        """Fetch from every source concurrently and return merged events.

        Args:
            prefetch_weather: When ``True`` each event's current weather is
                attached to ``metadata["weather"]`` (defaults to the pipeline
                config ``enrich_weather``).

        Returns:
            A list of :class:`CrisisEvent`. No exception is raised for
            individual source failures; inspect :attr:`last_result.source_errors`
            for details.
        """
        result = await self.run_with_errors(prefetch_weather=prefetch_weather)
        return result.events

    async def run_with_errors(
        self,
        *,
        prefetch_weather: bool | None = None,
    ) -> IngestionResult:
        """Like :meth:`run_all` but also surfaces per-source errors and timing."""
        result = IngestionResult()
        timeout = httpx.Timeout(self.config["timeout"])
        async with httpx.AsyncClient(timeout=timeout, headers=DEFAULT_HEADERS, follow_redirects=True) as client:
            tasks = {
                name: asyncio.create_task(self._fetch_safely(client, name, source))
                for name, source in self.sources.items()
            }
            fetched: dict[str, list[CrisisEvent]] = {}
            for name, task in tasks.items():
                events, error = await task
                fetched[name] = events
                if error is not None:
                    result.source_errors[name] = error

            if prefetch_weather is None:
                prefetch_weather = bool(self.config.get("enrich_weather", False))
            if prefetch_weather:
                all_events = [ev for sub in fetched.values() for ev in sub]
                await self.open_meteo.enrich_events(
                    client, all_events,
                    max_concurrent=int(self.config.get("max_weather_concurrency", 5)),
                )

        result.events = [ev for sub in fetched.values() for ev in sub]
        result.events.sort(key=lambda e: e.timestamp or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        result.finished_at = datetime.now(timezone.utc)
        self.last_result = result

        summary = ", ".join(f"{name}: {len(events)}" for name, events in fetched.items())
        logger.info("Ingestion finished in %.1fs [%s]", result.duration_seconds, summary)
        if result.source_errors:
            logger.warning("Sources with errors: %s", ", ".join(result.source_errors))
        return result

    async def fetch_source(self, name: str) -> list[CrisisEvent]:
        """Fetch from a single named source (e.g. ``"usgs"``)."""
        source = self.sources.get(name)
        if source is None:
            raise KeyError(f"Unknown source: {name!r}. Available: {list(self.sources)}")
        timeout = httpx.Timeout(self.config["timeout"])
        async with httpx.AsyncClient(timeout=timeout, headers=DEFAULT_HEADERS, follow_redirects=True) as client:
            events, error = await self._fetch_safely(client, name, source)
        if error is not None:
            raise error
        return events

    def preprocess(self, events: Sequence[CrisisEvent]) -> pd.DataFrame:
        """Run the full preprocessing pipeline over ``events``."""
        return preprocess_pipeline(events)

    async def run_preprocessed(self, **kwargs: Any) -> pd.DataFrame:
        """Fetch, then immediately preprocess, returning a DataFrame."""
        events = await self.run_all(**kwargs)
        return self.preprocess(events)

    def available_sources(self) -> list[str]:
        return list(self.sources)

    # -- internals -----------------------------------------------------------

    async def _fetch_safely(
        self,
        client: httpx.AsyncClient,
        name: str,
        source: Any,
    ) -> tuple[list[CrisisEvent], Exception | None]:
        """Run one source, converting any exception into an error result."""
        try:
            events = await source.fetch(client)
            return events or [], None
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - per-source error isolation
            logger.exception("Source %s failed", name)
            return [], exc


async def async_main() -> None:
    """Demo entry point (``python -m backend.data.ingestion``)."""
    logging.basicConfig(level=logging.INFO)
    pipeline = DataIngestionPipeline({"enrich_weather": True})
    result = await pipeline.run_with_errors()
    print(f"\nFetched {len(result.events)} events in {result.duration_seconds:.1f}s")
    if result.source_errors:
        print("Source failures:", ", ".join(result.source_errors))
    for event in result.events[:15]:
        print(f"  [{event.timestamp:%Y-%m-%d %H:%M}] {event.event_type:12s} "
              f"sev={event.severity} {event.country:20s} {event.title[:60]}")

    if result.events:
        df = pipeline.preprocess(result.events)
        print(f"\nPreprocessed DataFrame shape: {df.shape}")
        print(df[["source", "event_type", "severity", "region_risk_score", "season"]].head(10).to_string())


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()