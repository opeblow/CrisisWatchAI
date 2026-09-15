"""Alert generation and management service for CrisisWatch AI.

The alert service is responsible for turning ingested ``CrisisEvent`` records
into end-user alerts (only for events that cross the severity threshold),
querying active/recent alerts, tracking read state, and building the
human-readable alert messages that get surfaced in the dashboard,
notifications, and daily digests.

All methods are async and expect an ``AsyncSession`` that was injected at
construction time (typically via the FastAPI ``get_db`` dependency).
"""

from __future__ import annotations

from datetime import timezone
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models import CrisisAlert, CrisisEvent

#: Minimum event severity (1-5) that warrants spawning an alert.
ALERT_THRESHOLD = 4

_SEVERITY_LABELS: dict[int, str] = {
    1: "LOW",
    2: "MODERATE",
    3: "HIGH",
    4: "CRITICAL",
    5: "CATASTROPHIC",
}

_SEVERITY_COLORS: dict[int, str] = {
    1: "#737373",  # neutral gray
    2: "#D4D4D8",  # light gray
    3: "#EAB308",  # dark yellow
    4: "#FACC15",  # yellow
    5: "#FDE047",  # lemon
}


class AlertService:
    """Service responsible for creating, querying, and managing alerts.

    Args:
        session: The SQLAlchemy async session used for all database access.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------ #
    # Static severity helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def severity_label(severity_int: int) -> str:
        """Return the human label for a numeric crisis severity (1-5).

        Args:
            severity_int: A crisis severity score between 1 and 5.

        Returns:
            One of ``LOW``, ``MODERATE``, ``HIGH``, ``CRITICAL``,
            ``CATASTROPHIC``.

        Raises:
            ValueError: If the severity is not an integer in the range 1-5.
        """
        try:
            severity = int(severity_int)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(
                f"Severity must be an integer in the range 1-5, got "
                f"{severity_int!r}"
            ) from exc
        try:
            return _SEVERITY_LABELS[severity]
        except KeyError as exc:
            raise ValueError(
                f"Severity must be in the range 1-5, got {severity}"
            ) from exc

    @staticmethod
    def severity_color(severity_int: int) -> str:
        """Return the hex color associated with a crisis severity (1-5).

        Args:
            severity_int: A crisis severity score between 1 and 5.

        Returns:
            A hex color string such as ``#C62828`` for critical events.

        Raises:
            ValueError: If the severity is not an integer in the range 1-5.
        """
        try:
            severity = int(severity_int)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(
                f"Severity must be an integer in the range 1-5, got "
                f"{severity_int!r}"
            ) from exc
        try:
            return _SEVERITY_COLORS[severity]
        except KeyError as exc:
            raise ValueError(
                f"Severity must be in the range 1-5, got {severity}"
            ) from exc

    # ------------------------------------------------------------------ #
    # Alert lifecycle
    # ------------------------------------------------------------------ #
    async def check_new_crisis(self, crisis_event: CrisisEvent) -> dict[str, Any] | None:
        """Evaluate a crisis event and generate an alert when warranted.

        An alert is only created when the event's severity is at or above
        ``ALERT_THRESHOLD`` (4). Lower-severity events are tracked in the
        events table but do not produce alerts.

        Args:
            crisis_event: The crisis event to evaluate. Must be persisted so
                a foreign key reference can be stored on the alert.

        Returns:
            A serialized alert dict, or ``None`` when the event does not
            warrant an alert.

        Raises:
            ValueError: If the event severity is outside the valid 1-5 range.
        """
        try:
            severity = int(crisis_event.severity)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(
                f"Invalid severity {crisis_event.severity!r} on crisis event "
                f"{crisis_event.id}"
            ) from exc

        if not 1 <= severity <= 5:
            self.severity_label(severity)  # raises ValueError with a clear message

        if severity < ALERT_THRESHOLD:
            return None

        message = self.generate_alert_message(crisis_event)
        alert = CrisisAlert(
            crisis_event_id=crisis_event.id,
            severity=severity,
            message=message,
            is_read=False,
        )
        self._session.add(alert)
        await self._session.commit()
        await self._session.refresh(alert)
        return self._serialize_alert(alert, crisis_event)

    async def get_active_alerts(
        self,
        limit: int = 50,
        unread_only: bool = False,
    ) -> list[dict[str, Any]]:
        """Return the most recent alerts, newest and most severe first.

        Alerts are ordered by severity (descending) and then by time
        (descending), so the most critical recent alerts always appear first.

        Args:
            limit: Maximum number of alerts to return.
            unread_only: When ``True``, only return alerts that have not yet
                been marked as read.

        Returns:
            A list of serialized alert dicts (newest/most severe first).
        """
        stmt = (
            select(CrisisAlert)
            .options(selectinload(CrisisAlert.crisis_event))
            .order_by(CrisisAlert.severity.desc(), CrisisAlert.created_at.desc())
            .limit(limit)
        )
        if unread_only:
            stmt = stmt.where(CrisisAlert.is_read.is_(False))

        result = await self._session.execute(stmt)
        alerts = result.scalars().all()
        return [self._serialize_alert(alert) for alert in alerts]

    async def get_unread_count(self) -> int:
        """Return the number of alerts that have not yet been read."""
        stmt = (
            select(func.count())
            .select_from(CrisisAlert)
            .where(CrisisAlert.is_read.is_(False))
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def mark_as_read(self, alert_id: str) -> bool:
        """Mark a single alert as read.

        Args:
            alert_id: The UUID (as a string) of the alert to update.

        Returns:
            ``True`` when an alert was found and updated, ``False`` otherwise.
        """
        result = await self._session.execute(
            update(CrisisAlert)
            .where(CrisisAlert.id == alert_id)
            .values(is_read=True)
        )
        await self._session.commit()
        return result.rowcount is not None and result.rowcount > 0

    # ------------------------------------------------------------------ #
    # Message formatting
    # ------------------------------------------------------------------ #
    def generate_alert_message(self, event: CrisisEvent) -> str:
        """Build a human-readable alert message for a crisis event.

        The message summarizes severity, crisis type, location, and casualty
        figures so an operator can triage the alert without opening the full
        event detail.

        Args:
            event: The crisis event to describe.

        Returns:
            A single-line (newline-free) alert message string.
        """
        sever_label = self.severity_label(int(event.severity))
        event_type = getattr(event, "event_type", "unknown crisis")
        if hasattr(event_type, "value"):
            event_type = event_type.value
        event_type = str(event_type).replace("_", " ").title()

        location = f"{event.region}, {event.country}"
        parts: list[str] = [
            f"{sever_label} {event_type} detected in {location}"
        ]

        timestamp = getattr(event, "timestamp", None)
        if timestamp is not None:
            ts = timestamp
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            parts.append(f"occurring {ts.isoformat()}")

        casualties = getattr(event, "casualties", None)
        displaced = getattr(event, "displaced", None)
        affected = getattr(event, "affected", None)
        figures: list[str] = []
        if casualties:
            figures.append(f"Casualties: {casualties:,}")
        if displaced:
            figures.append(f"Displaced: {displaced:,}")
        if affected:
            figures.append(f"Affected: {affected:,}")
        if figures:
            parts.append("; ".join(figures))

        title = getattr(event, "title", None)
        if title:
            parts.append(f"Event: {title}")

        description = getattr(event, "description", None)
        if description:
            snippet = " ".join(str(description).split())
            if len(snippet) > 240:
                snippet = snippet[:240].rstrip() + "..."
            if snippet:
                parts.append(f"Details: {snippet}")

        return ". ".join(parts) + "."

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    def _serialize_alert(
        self,
        alert: CrisisAlert,
        event: CrisisEvent | None = None,
    ) -> dict[str, Any]:
        """Convert an alert ORM object (and optionally its event) to a dict."""
        payload: dict[str, Any] = {
            "id": alert.id,
            "crisis_event_id": alert.crisis_event_id,
            "severity": alert.severity,
            "severity_label": self.severity_label(alert.severity),
            "severity_color": self.severity_color(alert.severity),
            "message": alert.message,
            "is_read": bool(alert.is_read),
            "created_at": (
                alert.created_at.isoformat() if alert.created_at is not None else None
            ),
        }

        event = event or getattr(alert, "crisis_event", None)
        if event is not None:
            ts = getattr(event, "timestamp", None)
            event_type = getattr(event, "event_type", None)
            payload["crisis_event"] = {
                "id": getattr(event, "id", None),
                "title": getattr(event, "title", None),
                "event_type": (
                    event_type.value if hasattr(event_type, "value") else str(event_type)
                ),
                "severity": getattr(event, "severity", None),
                "region": getattr(event, "region", None),
                "country": getattr(event, "country", None),
                "latitude": getattr(event, "latitude", None),
                "longitude": getattr(event, "longitude", None),
                "timestamp": ts.isoformat() if ts is not None else None,
            }
        return payload