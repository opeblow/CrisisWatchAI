"""Reports router — auto-generated impact reports (markdown/HTML/PDF)."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_db
from db.models import CrisisEvent, Forecast, Report, ReportFormat
from services.report_service import ReportService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reports", tags=["reports"])


class GenerateReportRequest(BaseModel):
    region: str = Field(..., min_length=1, max_length=100)
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    format: str = Field("markdown", pattern="^(markdown|pdf)$")
    include_predictions: bool = True


def _report_to_dict(report: Report) -> dict[str, Any]:
    return {
        "id": report.id,
        "region": report.region,
        "date_from": report.date_from.isoformat(),
        "date_to": report.date_to.isoformat(),
        "content": report.content,
        "format": report.format.value,
        "created_at": report.created_at.isoformat() if report.created_at else None,
    }


@router.post("/generate", summary="Generate an impact report for a region/timeframe")
async def generate_report(
    req: GenerateReportRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    date_from = req.date_from or datetime.now(timezone.utc) - timedelta(days=90)
    date_to = req.date_to or datetime.now(timezone.utc)

    stmt = (
        select(CrisisEvent)
        .where(
            CrisisEvent.region == req.region,
            CrisisEvent.timestamp >= date_from,
            CrisisEvent.timestamp <= date_to,
        )
        .order_by(CrisisEvent.timestamp.desc())
    )
    rows = await db.execute(stmt)
    events = rows.scalars().all()
    if not events:
        raise HTTPException(
            status_code=404,
            detail=f"No crisis events for region '{req.region}' in the given window",
        )

    crises_data = [
        {
            "event_type": e.event_type.value,
            "title": e.title,
            "description": e.description,
            "severity": e.severity,
            "country": e.country,
            "region": e.region,
            "timestamp": e.timestamp,
            "casualties": e.casualties,
            "displaced": e.displaced,
            "affected": e.affected,
        }
        for e in events
    ]

    forecasts_data = []
    clusters_data = []
    if req.include_predictions:
        try:
            frows = await db.execute(
                select(Forecast).where(Forecast.region == req.region).order_by(Forecast.forecast_date.desc()).limit(10)
            )
            forecasts_data = [
                {
                    "date": f.forecast_date,
                    "predicted_count": f.predicted_count,
                    "confidence_lower": f.confidence_lower,
                    "confidence_upper": f.confidence_upper,
                }
                for f in frows.scalars().all()
            ]
        except Exception as exc:  # noqa: BLE001
            logger.warning("Forecast data unavailable for report: %s", exc)

    def build() -> str:
        service = ReportService()
        return service.generate_report(
            req.region,
            date_from,
            date_to,
            crises_data,
            forecasts_data,
            clusters_data,
        )

    content = await asyncio.to_thread(build)
    fmt = ReportFormat(req.format)
    report = Report(
        region=req.region,
        date_from=date_from,
        date_to=date_to,
        content=content,
        format=fmt,
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)
    return _report_to_dict(report)


@router.get("", summary="List generated reports")
async def list_reports(
    region: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    stmt = select(Report).order_by(Report.created_at.desc())
    if region:
        stmt = stmt.where(Report.region == region)
    rows = await db.execute(stmt.limit(limit))
    reports = rows.scalars().all()
    return {"reports": [_report_to_dict(r) for r in reports], "count": len(reports)}


@router.get("/{report_id}", summary="Get a single report")
async def get_report(report_id: str, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    row = await db.execute(select(Report).where(Report.id == report_id))
    report = row.scalar_one_or_none()
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return _report_to_dict(report)