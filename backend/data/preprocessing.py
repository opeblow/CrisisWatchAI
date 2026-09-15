"""Data preprocessing: cleaning, imputation, deduplication and feature
engineering on top of :class:`CrisisEvent` objects.

The module exposes a single entry point -- :func:`preprocess_pipeline` -- which
runs the full chain and returns a pandas DataFrame ready for ML consumption.
"""
from __future__ import annotations

import logging
import math
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from typing import Any, Dict, Iterable, List, Optional, Sequence

import pandas as pd

from .schema import CrisisEvent, DEFAULT_SEVERITY
from .utils import strip_html

logger = logging.getLogger(__name__)

# --- Severity normalization -------------------------------------------------

SOURCE_DEFAULT_SEVERITY = {"who": 3, "reliefweb": 3, "acled": 3, "nasa_firms": 2}


def normalize_severity(source: str, raw_severity: Any) -> int:
    """Coerce a raw severity from any upstream format to the unified 1-5 scale.

    Handles: numeric strings, floats, out-of-range values, ``None`` and empty
    values. Out-of-range values are clamped; missing values fall back to a
    per-source default.
    """
    try:
        if raw_severity is None or raw_severity == "":
            value = SOURCE_DEFAULT_SEVERITY.get(source, DEFAULT_SEVERITY)
        else:
            value = int(float(raw_severity))
    except (TypeError, ValueError):
        value = SOURCE_DEFAULT_SEVERITY.get(source, DEFAULT_SEVERITY)
    return max(1, min(5, value))


# --- Text cleaning ----------------------------------------------------------


def clean_text(text: Any, max_length: int = 1000) -> str:
    """Remove HTML, normalize unicode and whitespace, and truncate."""
    cleaned = strip_html(text)
    # Normalize unicode (compose/decompose to NFC) and collapse whitespace.
    cleaned = unicodedata.normalize("NFC", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if max_length and len(cleaned) > max_length:
        cleaned = cleaned[: max_length - 1].rstrip() + "…"
    return cleaned


# --- Coordinate -> country lookup ------------------------------------------

#: Cached reverse-geocoding results keyed by rounded (lat, lon).
_country_cache: Dict[tuple, str] = {}
_world = None


def _load_world():
    """Load the Natural Earth low-res world boundary dataset (lazy, cached)."""
    global _world
    if _world is not None:
        return _world
    try:
        import geopandas as gpd
        from shapely.geometry import Point

        path = gpd.datasets.get_path("naturalearth_lowres")
    except Exception:  # noqa: BLE001 - optional dependency / missing dataset
        logger.warning("geopandas/naturalearth unavailable; country lookup disabled")
        return None

    class Wrapper:
        pass

    world = Wrapper()
    world.gdf = gpd.read_file(path)
    world.gdf = world.gdf[world.gdf["continent"] != "Seven seas (open ocean)"]
    world.point_cls = Point
    _world = world
    return _world


def extract_country_from_coords(lat: float, lon: float) -> str:
    """Reverse-geocode WGS84 coordinates to a country name (offline, cached).

    Uses a point-in-polygon test against Natural Earth low-resolution
    boundaries. Returns ``""`` for unknown/ocean coordinates.
    """
    if lat is None or lon is None or math.isnan(float(lat)) or math.isnan(float(lon)):
        return ""
    lat, lon = float(lat), float(lon)
    key = (round(lat, 2), round(lon, 2))
    if key in _country_cache:
        return _country_cache[key]

    world = _load_world()
    if world is None:
        return ""

    result = ""
    try:
        point = world.point_cls(lon, lat)
        sindex = world.gdf.sindex
        candidates = list(sindex.query(point.bounds))
        for idx in candidates:
            if world.gdf.geometry.iloc[idx].contains(point):
                result = str(world.gdf.iloc[idx]["NAME"])
                break
    except Exception as exc:  # noqa: BLE001 - geospatial ops can fail on bad data
        logger.warning("Country lookup failed for (%s, %s): %s", lat, lon, exc)

    _country_cache[key] = result
    return result


# --- Imputation -------------------------------------------------------------


def impute_missing(events: Sequence[CrisisEvent]) -> List[CrisisEvent]:
    """Fill missing fields using best-effort heuristics (mutates in place).

    - Severity: normalized to 1-5 (see :func:`normalize_severity`).
    - Country/region: derived from coordinates when empty.
    - Timestamp: defaults to "now" when missing.
    - Casualties/affected/displaced: left as ``None`` (unknown) unless a
      source can supply them.
    """
    now = datetime.now(timezone.utc)
    for event in events:
        event.severity = normalize_severity(event.source, event.severity)

        if not event.country.strip():
            event.country = extract_country_from_coords(event.latitude, event.longitude)
        if not event.region.strip():
            event.region = (
                event.country
                or extract_country_from_coords(event.latitude, event.longitude)
                or "Unknown"
            )
        if event.timestamp is None:
            event.timestamp = now
        elif event.timestamp.tzinfo is None:
            event.timestamp = event.timestamp.replace(tzinfo=timezone.utc)
        if not event.title.strip():
            event.title = f"{event.event_type} alert"
        if not event.description.strip():
            event.description = event.title
    return list(events)


# --- Deduplication ----------------------------------------------------------


def _dedup_key(event: CrisisEvent) -> tuple:
    """Grouping key for cross-source deduplication.

    Uses event type + rounded coordinates + calendar day. Events without
    coordinates fall back to a title-based key.
    """
    has_coords = (
        not math.isnan(float(event.latitude))
        and not math.isnan(float(event.longitude))
    )
    if has_coords:
        lat = round(float(event.latitude), 2)
        lon = round(float(event.longitude), 2)
    else:
        lat = lon = None
    date = event.timestamp.date() if event.timestamp else None
    return (event.event_type, lat, lon, date)


def _dedup_title_key(event: CrisisEvent) -> str:
    """Normalized title used for near-duplicate text comparison."""
    return unicodedata.normalize("NFC", re.sub(r"[\W_]+", " ", event.title.lower()).strip())


def _event_completeness(event: CrisisEvent) -> tuple:
    """Sort key expressing how much data an event carries."""
    return (
        event.severity,
        1 if event.casualties is not None else 0,
        1 if event.displaced is not None else 0,
        1 if event.affected is not None else 0,
        len(event.description),
        len(event.metadata),
    )


def _merge_events(a: CrisisEvent, b: CrisisEvent) -> CrisisEvent:
    """Merge event ``b`` into ``a``, keeping the richer values for each field."""
    merged = CrisisEvent(
        source=a.source,
        event_type=a.event_type,
        title=a.title or b.title,
        description=a.description or b.description,
        severity=max(a.severity, b.severity),
        latitude=a.latitude if not math.isnan(float(a.latitude)) else b.latitude,
        longitude=a.longitude if not math.isnan(float(a.longitude)) else b.longitude,
        country=a.country or b.country,
        region=a.region or b.region,
        timestamp=min((t for t in (a.timestamp, b.timestamp) if t), default=None)
        or datetime.now(timezone.utc),
        casualties=a.casualties if a.casualties is not None else b.casualties,
        displaced=a.displaced if a.displaced is not None else b.displaced,
        affected=a.affected if a.affected is not None else b.affected,
        raw_data={**b.raw_data, **a.raw_data},
        metadata={**b.metadata, **a.metadata},
    )
    merged.metadata["merged_sources"] = sorted(
        set(merged.metadata.get("merged_sources", [])) | {a.source, b.source}
    )
    return merged


def deduplicate(events: Sequence[CrisisEvent]) -> List[CrisisEvent]:
    """Remove duplicates across sources.

    Two passes:

    1. Structural: group by type + coordinates + day, keep the most complete
       event per group.
    2. Semantic: collapse near-identical titles (>= ``similarity_threshold``
       sequence match) on the same day.
    """
    if not events:
        return []

    structural: Dict[tuple, List[CrisisEvent]] = defaultdict(list)
    for event in events:
        structural[_dedup_key(event)].append(event)

    deduped: List[CrisisEvent] = []
    for group in structural.values():
        if len(group) == 1:
            deduped.append(group[0])
            continue
        best = max(group, key=_event_completeness)
        for other in group:
            if other is best:
                continue
            best = _merge_events(best, other)
        deduped.append(best)

    # Pass 2: semantic near-duplicate collapse.
    result: List[CrisisEvent] = []

    def _is_duplicate(candidate: CrisisEvent, existing: CrisisEvent) -> bool:
        if candidate.event_type != existing.event_type:
            return False
        if candidate.timestamp and existing.timestamp:
            if abs((candidate.timestamp - existing.timestamp).days) > 1:
                return False
        elif _dedup_key(candidate) != _dedup_key(existing):
            return False
        title_a, title_b = _dedup_title_key(candidate), _dedup_title_key(existing)
        if not title_a or not title_b:
            return False
        return SequenceMatcher(None, title_a, title_b).ratio() >= 0.9

    for event in deduped:
        replace_with = event
        for i, kept in enumerate(result):
            if _is_duplicate(event, kept):
                replace_with = _merge_events(
                    max(event, kept, key=_event_completeness),
                    min(event, kept, key=_event_completeness),
                )
                result[i] = replace_with
                break
        else:
            result.append(event)

    return result


# --- Feature engineering ----------------------------------------------------

_COUNTRY_RISK = {
    "Afghanistan": 0.9, "Syria": 0.9, "Somalia": 0.88, "Yemen": 0.87,
    "Ukraine": 0.85, "Ethiopia": 0.82, "Sudan": 0.8, "Myanmar": 0.78,
    "Haiti": 0.78, "Philippines": 0.77, "Bangladesh": 0.75, "Nepal": 0.7,
    "India": 0.7, "Indonesia": 0.72, "Pakistan": 0.75, "Iran": 0.72,
    "Turkey": 0.7, "Japan": 0.65, "China": 0.65, "Mexico": 0.66,
    "Guatemala": 0.74, "El Salvador": 0.71, "Honduras": 0.73, "Chile": 0.6,
    "Peru": 0.63, "Ecuador": 0.64, "Colombia": 0.66, "Venezuela": 0.78,
}
_TYPE_RISK = {
    "earthquake": 0.7, "cyclone": 0.75, "flood": 0.7, "drought": 0.65,
    "epidemic": 0.75, "conflict": 0.85, "wildfire": 0.55, "displacement": 0.8,
}
_DEFAULT_COUNTRY_RISK = 0.5


def _season(month: int, latitude: float) -> str:
    """Meteorological season in the event's hemisphere."""
    if month in (12, 1, 2):
        season_north = "winter"
    elif month in (3, 4, 5):
        season_north = "spring"
    elif month in (6, 7, 8):
        season_north = "summer"
    else:
        season_north = "autumn"
    if latitude is None or math.isnan(float(latitude)):
        return season_north
    if float(latitude) < 0:
        return {
            "winter": "summer", "spring": "autumn",
            "summer": "winter", "autumn": "spring",
        }[season_north]
    return season_north


def feature_engineering(events: Sequence[CrisisEvent]) -> List[Dict[str, Any]]:
    """Derive predictive features for each event.

    Produces one flat dict per event containing the base fields plus:

    - ``time_of_day``: hour of day (0-23),
    - ``day_of_week``: ISO weekday (0=Monday ... 6=Sunday),
    - ``season``: meteorological season by hemisphere,
    - ``region_risk_score``: static country-driven risk (0-1).
    """
    records: List[Dict[str, Any]] = []
    for event in events:
        ts = event.timestamp
        record = {
            "source": event.source,
            "event_type": event.event_type,
            "severity": event.severity,
            "latitude": event.latitude,
            "longitude": event.longitude,
            "country": event.country,
            "region": event.region,
            "timestamp": ts,
            "casualties": event.casualties,
            "displaced": event.displaced,
            "affected": event.affected,
            "title": event.title,
            "description": event.description,
            "time_of_day": ts.hour if ts else None,
            "day_of_week": ts.weekday() if ts else None,
            "season": _season(ts.month if ts else 0, event.latitude),
            "region_risk_score": _region_risk_score(event),
        }
        record.update({f"w_{k}": v for k, v in event.metadata.items() if k != "weather"})
        record["weather"] = event.metadata.get("weather", {})
        records.append(record)
    return records


def _region_risk_score(event: CrisisEvent) -> float:
    """Blend a static country risk index with event-type risk (0-1)."""
    country_risk = _COUNTRY_RISK.get(event.country, _DEFAULT_COUNTRY_RISK)
    type_risk = _TYPE_RISK.get(event.event_type, 0.5)
    severity_boost = (event.severity - 1) * 0.08
    return round(min(1.0, max(0.0, 0.6 * country_risk + 0.4 * type_risk + severity_boost)), 3)


# --- Full pipeline ----------------------------------------------------------

_FEATURE_COLUMNS = [
    "source", "event_type", "severity", "latitude", "longitude", "country",
    "region", "timestamp", "casualties", "displaced", "affected", "title",
    "description", "time_of_day", "day_of_week", "season", "region_risk_score",
    "weather",
]


def preprocess_pipeline(events: Sequence[CrisisEvent]) -> pd.DataFrame:
    """Run cleaning -> imputation -> deduplication -> feature engineering and
    return the result as a pandas DataFrame."""
    cleaned: List[CrisisEvent] = []
    for event in events:
        cleaned.append(
            CrisisEvent(
                source=event.source,
                event_type=event.event_type,
                title=clean_text(event.title),
                description=clean_text(event.description, max_length=1500),
                severity=normalize_severity(event.source, event.severity),
                latitude=event.latitude,
                longitude=event.longitude,
                country=clean_text(event.country, max_length=80),
                region=clean_text(event.region, max_length=80),
                timestamp=event.timestamp,
                casualties=event.casualties,
                displaced=event.displaced,
                affected=event.affected,
                raw_data=event.raw_data,
                metadata=dict(event.metadata),
            )
        )

    imputed = impute_missing(cleaned)
    deduped = deduplicate(imputed)
    records = feature_engineering(deduped)

    df = pd.DataFrame(records)
    for column in _FEATURE_COLUMNS:
        if column not in df.columns:
            df[column] = None
    # Ensure predictable column ordering.
    return df[_FEATURE_COLUMNS]