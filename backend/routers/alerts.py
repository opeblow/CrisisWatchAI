"""Alerts router — active crisis alerts, unread counts, read-state management."""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.database import get_db
from db.models import CrisisAlert, CrisisEvent
from services.alert_service import AlertService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


def _serialize(alert: CrisisAlert) -> dict[str, Any]:
    event = alert.crisis_event
    return {
        "id": alert.id,
        "crisis_event_id": alert.crisis_event_id,
        "severity": alert.severity,
        "severity_label": AlertService.severity_label(alert.severity),
        "severity_color": AlertService.severity_color(alert.severity),
        "message": alert.message,
        "is_read": alert.is_read,
        "created_at": alert.created_at.isoformat() if alert.created_at else None,
        "event": {
            "event_type": event.event_type.value if event else None,
            "title": event.title if event else None,
            "country": event.country if event else None,
            "region": event.region if event else None,
            "latitude": event.latitude if event else None,
            "longitude": event.longitude if event else None,
            "timestamp": event.timestamp.isoformat() if event and event.timestamp else None,
        },
    }


@router.get("", summary="Get active alerts sorted by urgency")
async def get_alerts(
    severity_min: Optional[int] = Query(None, ge=1, le=5),
    unread_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    stmt = (
        select(CrisisAlert)
        .options(selectinload(CrisisAlert.crisis_event))
        .order_by(CrisisAlert.severity.desc(), CrisisAlert.created_at.desc())
    )
    if severity_min is not None:
        stmt = stmt.where(CrisisAlert.severity >= severity_min)
    if unread_only:
        stmt = stmt.where(CrisisAlert.is_read.is_(False))
    rows = await db.execute(stmt.limit(limit))
    alerts = rows.scalars().all()

    unread = (
        await db.execute(
            select(func.count()).select_from(CrisisAlert).where(CrisisAlert.is_read.is_(False))
        )
    ).scalar_one()

    return {
        "alerts": [_serialize(a) for a in alerts],
        "count": len(alerts),
        "unread_count": unread,
        "pipeline": "severity >= threshold auto-triggered",
    }


@router.get("/unread-count", summary="Number of unread alerts")
async def unread_count(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    unread = (
        await db.execute(
            select(func.count()).select_from(CrisisAlert).where(CrisisAlert.is_read.is_(False))
        )
    ).scalar_one()
    return {"unread_count": unread}


@router.patch("/{alert_id}/read", summary="Mark an alert as read")
async def mark_read(alert_id: str, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    row = await db.execute(select(CrisisAlert).where(CrisisAlert.id == alert_id))
    alert = row.scalar_one_or_none()
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.is_read = True
    await db.commit()
    return {"id": alert.id, "is_read": True}


@router.post("", summary="Synthesize alerts from recent high-severity events")
async def synthesize_alerts(
    threshold: int = Query(4, ge=1, le=5),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Demo/onboarding endpoint — derive pending alerts from stored crisis events."""
    existing = {
        r[0]
        for r in (
            await db.execute(select(CrisisAlert.crisis_event_id).where(CrisisAlert.is_read.is_(False)))
        ).all()
    }
    events = (
        await db.execute(
            select(CrisisEvent)
            .where(CrisisEvent.severity >= threshold)
            .limit(100)
        )
    ).scalars().all()
    created = 0
    for ev in events:
        if ev.id in existing:
            continue
        message = AlertService(None).generate_alert_message(ev)
        db.add(
            CrisisAlert(
                crisis_event_id=ev.id,
                severity=ev.severity,
                message=message,
                is_read=False,
            )
        )
        created += 1
    await db.commit()
    return {"created": created, "threshold": threshold}