from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.database import Base


class CrisisEventType(str, enum.Enum):
    earthquake = "earthquake"
    flood = "flood"
    cyclone = "cyclone"
    drought = "drought"
    wildfire = "wildfire"
    epidemic = "epidemic"
    conflict = "conflict"
    displacement = "displacement"


class ReportFormat(str, enum.Enum):
    pdf = "pdf"
    markdown = "markdown"


class CrisisEvent(Base):
    __tablename__ = "crisis_events"
    __table_args__ = (
        Index("ix_crisis_events_event_type", "event_type"),
        Index("ix_crisis_events_country", "country"),
        Index("ix_crisis_events_region", "region"),
        Index("ix_crisis_events_severity", "severity"),
        Index("ix_crisis_events_timestamp", "timestamp"),
        Index("ix_crisis_events_created_at", "created_at"),
        Index("ix_crisis_events_location", "latitude", "longitude"),
        CheckConstraint("severity >= 1 AND severity <= 5", name="ck_severity_range"),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    source: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[CrisisEventType] = mapped_column(
        Enum(CrisisEventType, name="crisis_event_type", native_enum=False),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    severity: Mapped[int] = mapped_column(Integer, nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    country: Mapped[str] = mapped_column(String(100), nullable=False)
    region: Mapped[str] = mapped_column(String(100), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    casualties: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    displaced: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    affected: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    raw_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSON, nullable=True)
    location = None  # PostGIS geometry — populated via SQLAlchemy column at runtime if PostGIS is available
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    alerts: Mapped[list[CrisisAlert]] = relationship(
        "CrisisAlert", back_populates="crisis_event", cascade="all, delete-orphan"
    )
    predictions: Mapped[list[Prediction]] = relationship(
        "Prediction", back_populates="crisis_event", cascade="all, delete-orphan"
    )


class CrisisAlert(Base):
    __tablename__ = "crisis_alerts"
    __table_args__ = (
        Index("ix_crisis_alerts_is_read", "is_read"),
        Index("ix_crisis_alerts_created_at", "created_at"),
        Index("ix_crisis_alerts_severity", "severity"),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    crisis_event_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("crisis_events.id", ondelete="CASCADE"),
        nullable=False,
    )
    severity: Mapped[int] = mapped_column(Integer, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    crisis_event: Mapped[CrisisEvent] = relationship("CrisisEvent", back_populates="alerts")


class Prediction(Base):
    __tablename__ = "predictions"
    __table_args__ = (
        Index("ix_predictions_prediction_type", "prediction_type"),
        Index("ix_predictions_created_at", "created_at"),
        Index("ix_predictions_model_version", "model_version"),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    crisis_event_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("crisis_events.id", ondelete="SET NULL"),
        nullable=True,
    )
    prediction_type: Mapped[str] = mapped_column(String(100), nullable=False)
    predicted_value: Mapped[dict] = mapped_column(JSON, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    shap_values: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    model_version: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    crisis_event: Mapped[Optional[CrisisEvent]] = relationship(
        "CrisisEvent", back_populates="predictions"
    )


class Forecast(Base):
    __tablename__ = "forecasts"
    __table_args__ = (
        Index("ix_forecasts_region", "region"),
        Index("ix_forecasts_crisis_type", "crisis_type"),
        Index("ix_forecasts_forecast_date", "forecast_date"),
        Index("ix_forecasts_region_type_date", "region", "crisis_type", "forecast_date"),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    region: Mapped[str] = mapped_column(String(100), nullable=False)
    crisis_type: Mapped[str] = mapped_column(String(50), nullable=False)
    forecast_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    predicted_count: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_lower: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_upper: Mapped[float] = mapped_column(Float, nullable=False)
    model_version: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Report(Base):
    __tablename__ = "reports"
    __table_args__ = (
        Index("ix_reports_region", "region"),
        Index("ix_reports_date_range", "date_from", "date_to"),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    region: Mapped[str] = mapped_column(String(100), nullable=False)
    date_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    date_to: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    format: Mapped[ReportFormat] = mapped_column(
        Enum(ReportFormat, name="report_format", native_enum=False),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
