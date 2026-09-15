"""Unified crisis event schema shared by all ingestion sources.

Defines the canonical :class:`CrisisEvent` dataclass that every data source
produces. Keeping the schema in its own module avoids circular imports between
the ingestion orchestrator (``ingestion.py``) and the per-source parser modules.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional

#: Canonical crisis categories the pipeline normalizes every event into.
EVENT_TYPES = (
    "earthquake",
    "flood",
    "cyclone",
    "drought",
    "wildfire",
    "epidemic",
    "conflict",
    "displacement",
)

#: Sentinel used when a source does not provide coordinates.
UNKNOWN_COORD = float("nan")

#: Default severity used when a source cannot determine one (1-5 scale).
DEFAULT_SEVERITY = 3


@dataclass
class CrisisEvent:
    """A normalized crisis event produced by any ingestion source.

    Attributes:
        source: Which provider produced the event (``gdacs``, ``usgs``, ...).
        event_type: One of :data:`EVENT_TYPES`.
        title: Short human-readable event title.
        description: Longer free-text description (HTML tags stripped).
        severity: Unified impact severity between 1 and 5.
        latitude / longitude: WGS84 coordinates; ``UNKNOWN_COORD`` when missing.
        country: ISO-style country name; empty string when unknown.
        region: Sub-national region / administrative area; empty when unknown.
        timestamp: Aware UTC timestamp of when the event occurred.
        casualties / displaced / affected: Optional impact counts (or ``None``).
        raw_data: Original payload slice from the provider (for audit/replay).
        metadata: Source-specific extras (links, magnitudes, flags, ...).
    """

    source: str
    event_type: str
    title: str
    description: str
    severity: int
    latitude: float
    longitude: float
    country: str
    region: str
    timestamp: datetime
    casualties: Optional[int] = None
    displaced: Optional[int] = None
    affected: Optional[int] = None
    raw_data: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-friendly dictionary representation."""
        return {
            "source": self.source,
            "event_type": self.event_type,
            "title": self.title,
            "description": self.description,
            "severity": self.severity,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "country": self.country,
            "region": self.region,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "casualties": self.casualties,
            "displaced": self.displaced,
            "affected": self.affected,
            "raw_data": self.raw_data,
            "metadata": self.metadata,
        }