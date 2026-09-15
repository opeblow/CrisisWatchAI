"""Crisis events router — CRUD, filtering, map GeoJSON, and aggregations."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.database import get_db
from db.models import CrisisEvent, CrisisEventType

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/crises", tags=["crises"])

SEVERITY_LABELS = {
    1: "LOW",
    2: "MODERATE",
    3: "HIGH",
    4: "CRITICAL",
    5: "CATASTROPHIC",
}


def _serialize(event: CrisisEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "source": event.source,
        "event_type": event.event_type.value,
        "title": event.title,
        "description": event.description,
        "severity": event.severity,
        "severity_label": SEVERITY_LABELS.get(event.severity, "UNKNOWN"),
        "latitude": event.latitude,
        "longitude": event.longitude,
        "country": event.country,
        "region": event.region,
        "timestamp": event.timestamp.isoformat() if event.timestamp else None,
        "casualties": event.casualties,
        "displaced": event.displaced,
        "affected": event.affected,
        "metadata": event.metadata_ or {},
        "created_at": event.created_at.isoformat() if event.created_at else None,
    }


def _apply_filters(
    stmt: Any,
    event_type: str | None,
    severity_min: int | None,
    severity_max: int | None,
    country: str | None,
    region: str | None,
    date_from: datetime | None,
    date_to: datetime | None,
) -> Any:
    if event_type:
        try:
            et = CrisisEventType(event_type)
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Invalid event_type: {event_type}") from None
        stmt = stmt.where(CrisisEvent.event_type == et)
    if severity_min is not None:
        stmt = stmt.where(CrisisEvent.severity >= severity_min)
    if severity_max is not None:
        stmt = stmt.where(CrisisEvent.severity <= severity_max)
    if country:
        stmt = stmt.where(func.lower(CrisisEvent.country) == country.strip().lower())
    if region:
        stmt = stmt.where(func.lower(CrisisEvent.region) == region.strip().lower())
    if date_from:
        stmt = stmt.where(CrisisEvent.timestamp >= date_from)
    if date_to:
        stmt = stmt.where(CrisisEvent.timestamp <= date_to)
    return stmt


@router.get("", summary="List crisis events")
async def list_crises(
    event_type: str | None = Query(None, description="Filter by event type"),
    severity_min: int | None = Query(None, ge=1, le=5),
    severity_max: int | None = Query(None, ge=1, le=5),
    country: str | None = Query(None),
    region: str | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    base = _apply_filters(
        select(CrisisEvent), event_type, severity_min, severity_max, country, region, date_from, date_to
    )
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = await db.execute(base.order_by(CrisisEvent.timestamp.desc()).limit(limit).offset(offset))
    events = rows.scalars().all()
    return {"total": total, "limit": limit, "offset": offset, "events": [_serialize(e) for e in events]}


@router.get("/map", summary="Crisis events as GeoJSON for map rendering")
async def crises_geojson(
    event_type: str | None = Query(None),
    severity_min: int | None = Query(None, ge=1, le=5),
    severity_max: int | None = Query(None, ge=1, le=5),
    country: str | None = Query(None),
    region: str | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    base = _apply_filters(
        select(CrisisEvent), event_type, severity_min, severity_max, country, region, date_from, date_to
    )
    rows = await db.execute(base.order_by(CrisisEvent.timestamp.desc()))
    events = rows.scalars().all()

    features = []
    for e in events:
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [e.longitude, e.latitude]},
                "properties": {
                    "id": e.id,
                    "event_type": e.event_type.value,
                    "title": e.title,
                    "description": e.description,
                    "severity": e.severity,
                    "severity_label": SEVERITY_LABELS.get(e.severity, "UNKNOWN"),
                    "country": e.country,
                    "region": e.region,
                    "timestamp": e.timestamp.isoformat() if e.timestamp else None,
                    "casualties": e.casualties,
                    "displaced": e.displaced,
                    "affected": e.affected,
                },
            }
        )
    return {"type": "FeatureCollection", "features": features, "count": len(features)}


@router.get("/stats", summary="Aggregate crisis statistics")
async def crisis_stats(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    total = (
        await db.execute(select(func.count()).select_from(CrisisEvent))
    ).scalar_one()

    by_type_rows = await db.execute(
        select(CrisisEvent.event_type, func.count()).group_by(CrisisEvent.event_type)
    )
    by_type = {str(k.value): v for k, v in by_type_rows.all()}

    by_severity_rows = await db.execute(
        select(CrisisEvent.severity, func.count())
        .group_by(CrisisEvent.severity)
        .order_by(CrisisEvent.severity)
    )
    by_severity = {int(k): v for k, v in by_severity_rows.all()}

    countries = (
        await db.execute(select(func.count(func.distinct(CrisisEvent.country))))
    ).scalar_one()

    by_country_rows = await db.execute(
        select(CrisisEvent.country, func.count())
        .group_by(CrisisEvent.country)
        .order_by(func.count().desc())
        .limit(10)
    )
    top_countries = [{"country": c, "count": n} for c, n in by_country_rows.all()]

    recent_30d = datetime.now(timezone.utc).replace(tzinfo=None) - __import__(
        "datetime", fromlist=["timedelta"]
    ).timedelta(days=30)
    active_30d = (
        await db.execute(
            select(func.count())
            .select_from(CrisisEvent)
            .where(CrisisEvent.timestamp >= recent_30d)
        )
    ).scalar_one()

    critical = sum(int(k) for k, v in by_severity.items() if int(k) >= 4 and v > 0)

    return {
        "total_events": total,
        "active_last_30d": active_30d,
        "countries_impacted": countries,
        "critical_ongoing": critical,
        "by_type": by_type,
        "by_severity": by_severity,
        "top_countries": top_countries,
    }


@router.get("/regions", summary="List distinct regions with event counts")
async def list_regions(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    rows = await db.execute(
        select(
            CrisisEvent.region,
            func.count().label("count"),
            func.max(CrisisEvent.severity).label("max_severity"),
        )
        .group_by(CrisisEvent.region)
        .order_by(func.count().desc())
    )
    regions = [
        {"region": r, "count": c, "max_severity": s if s is not None else 1}
        for r, c, s in rows.all()
    ]
    return {"regions": regions}


@router.get("/{crisis_id}", summary="Get a single crisis event by ID")
async def get_crisis(crisis_id: str, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    row = await db.execute(
        select(CrisisEvent).options(selectinload(CrisisEvent.predictions)).where(CrisisEvent.id == crisis_id)
    )
    event = row.scalar_one_or_none()
    if event is None:
        raise HTTPException(status_code=404, detail="Crisis event not found")
    data = _serialize(event)
    data["predictions"] = [
        {
            "id": p.id,
            "prediction_type": p.prediction_type,
            "predicted_value": p.predicted_value,
            "confidence": p.confidence,
            "shap_values": p.shap_values,
            "model_version": p.model_version,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p in event.predictions
    ]
    return data