"""Report generation service for CrisisWatch AI.

Produces structured situation reports (Markdown), converts them to HTML, and
generates branded PDF documents via ReportLab. The pipeline is deliberately
pure: ``generate_report`` receives already-fetched data (crisis events,
forecasts, and cluster/risk groups) as plain dicts, so it can be used by
routers, scheduled jobs, and offline tooling alike.
"""

from __future__ import annotations

import os
from collections import Counter
from collections.abc import Sequence
from datetime import date, datetime, time, timezone
from html import escape as html_escape
from html.parser import HTMLParser
from math import log1p
from statistics import mean
from typing import Any

from services.alert_service import AlertService

severity_label = AlertService.severity_label
severity_color = AlertService.severity_color

# --------------------------------------------------------------------------- #
# Markdown rendering helpers
# --------------------------------------------------------------------------- #

_ACTION_TEMPLATES: dict[int, tuple[str, list[str]]] = {
    5: (
        "Catastrophic impact",
        [
            "Activate the highest emergency response protocol and alert national/international disaster-management bureaus immediately.",
            "Authorize and resource mass evacuation of the most exposed population centers without delay.",
            "Deploy field assessment teams within 6 hours and stand up continuous multi-agency coordination.",
            "Request international assistance (UN OCHA / Red Cross) early, including medical surge capacity.",
            "Establish emergency supply chains for food, water, shelter, and medicine in affected areas.",
        ],
    ),
    4: (
        "Critical impact",
        [
            "Stand up the regional crisis command center and elevate incident response to critical.",
            "Issue public safety notices and begin targeted evacuation of high-risk districts.",
            "Mobilize emergency response units and pre-position relief assets near affected zones.",
            "Escalate monitoring frequency for all active crises to an hourly review.",
            "Prepare early requests for federal/national contingency support.",
        ],
    ),
    3: (
        "High impact",
        [
            "Increase monitoring tempo and dispatch rapid assessment teams to affected areas.",
            "Publish situation reports for emergency managers and coordinate with humanitarian partners.",
            "Pre-position supplies and confirm evacuation routes while conditions are still stable.",
            "Review weekly ML forecasts for escalation signals in neighboring regions.",
        ],
    ),
    2: (
        "Elevated watch",
        [
            "Maintain the standard monitoring cadence and refresh crisis profiles bi-weekly.",
            "Keep stakeholders informed through periodic situation summaries.",
            "Rehearse response plans and verify contact rosters for high-risk areas.",
        ],
    ),
    1: (
        "Low impact",
        [
            "Continue routine monitoring and periodic data-quality reviews.",
            "Archive low-severity events and rely on system alerts for escalation detection.",
        ],
    ),
}

_UNIVERSAL_ACTIONS: list[str] = [
    "Verify and cross-check event data against primary sources before public release.",
    "Compare new events against active ML forecasts and annotate any divergences.",
    "Update the regional risk register and keep shared situational awareness current.",
]


def _to_datetime(value: Any) -> datetime:
    """Coerce a date, datetime, or ISO string into an aware datetime."""
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, date):
        dt = datetime.combine(value, time())
    elif isinstance(value, str):
        raise_invalid = False
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            raise_invalid = True
        if raise_invalid:
            raise ValueError(f"Unrecognized date/time value: {value!r}")
    else:
        raise TypeError(f"Cannot interpret {value!r} as a date/time")

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _format_date(dt: datetime) -> str:
    """Format a datetime as ``YYYY-MM-DD``."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d")


def _field(item: dict[str, Any], key: str, default: Any = None) -> Any:
    """Return ``item[key]`` if it is set and not None, else ``default``."""
    if not isinstance(item, dict):
        return default
    value = item.get(key, default)
    return default if value is None else value


def _event_type_label(item: dict[str, Any]) -> str:
    """Return a humanized crisis type string ('wild_fire' -> 'Wild Fire')."""
    event_type = _field(item, "event_type", "unknown")
    if hasattr(event_type, "value"):
        event_type = event_type.value
    return str(event_type).replace("_", " ").title()


def _severity_of(item: dict[str, Any], default: int = 1) -> int:
    """Coerce an item severity to a valid 1-5 integer."""
    try:
        severity = int(_field(item, "severity", default))
    except (TypeError, ValueError, OverflowError):
        severity = default
    return max(1, min(5, severity))


def _md_cell(value: Any) -> str:
    """Sanitize a value for safe placement inside a Markdown table cell."""
    text = str(value) if value is not None else ""
    return text.replace("|", "\\|").replace("\n", " ").replace("\r", "")


def _md_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> list[str]:
    """Render a list of markdown table lines from headers and rows."""
    lines = [
        "| " + " | ".join(_md_cell(h) for h in headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(_md_cell(c) for c in row) + " |")
    return lines


# --------------------------------------------------------------------------- #
# Report service
# --------------------------------------------------------------------------- #


class ReportService:
    """Generates structured crisis situation reports for a region and window.

    The service is stateless; every public method takes its data as arguments
    and returns strings/files, which keeps it easy to test and safe to call
    from background workers.
    """

    def __init__(self) -> None:
        pass

    # ------------------------------------------------------------------ #
    # Top-level API
    # ------------------------------------------------------------------ #
    def generate_report(
        self,
        region: str,
        date_from: Any,
        date_to: Any,
        crises_data: Sequence[dict[str, Any]],
        forecasts_data: Sequence[dict[str, Any]],
        clusters_data: Sequence[dict[str, Any]],
    ) -> str:
        """Generate a full situation report in Markdown.

        Args:
            region: Region the report covers.
            date_from: Start of the reporting window (date, datetime, or ISO string).
            date_to: End of the reporting window (date, datetime, or ISO string).
            crises_data: Crisis event dicts (``severity``, ``event_type``,
                ``region``, ``country``, ``casualties``, ``affected``, ...).
            forecasts_data: ML forecast dicts (``crisis_type``, ``forecast_date``,
                ``predicted_count``, ``confidence_lower``, ``confidence_upper``,
                ``model_version``, ...).
            clusters_data: Risk cluster dicts (``label``, ``size``, ``risk_score``,
                ``avg_severity``, ``dominant_type``, ``description``, ...).

        Returns:
            The report rendered as a Markdown string.
        """
        data = self._build_report_data(
            region=region,
            date_from=date_from,
            date_to=date_to,
            crises_data=crises_data or (),
            forecasts_data=forecasts_data or (),
            clusters_data=clusters_data or (),
        )
        return self.to_markdown(data)

    def to_markdown(self, data: dict[str, Any]) -> str:
        """Render a report data structure as a Markdown string."""
        region = data.get("region") or "Global"
        ex = data["executive_summary"]
        lines: list[str] = [
            "# CrisisWatch AI — Regional Situation Report",
            "",
            f"**Region:** {region}",
            f"**Reporting window:** {data['date_from_label']} to {data['date_to_label']}",
            f"**Generated:** {data['generated_at']} UTC",
            "",
            "---",
            "",
            "## 1. Executive Summary",
            "",
            f"- **Events reported:** {ex['total_events']}",
            f"- **Countries / areas affected:** {ex['countries_count']}",
            f"- **Total people affected:** {ex['total_affected']:,}",
            f"- **Confirmed casualties:** {ex['total_casualties']:,}",
            f"- **People displaced:** {ex['total_displaced']:,}",
            f"- **Peak severity:** {ex['max_severity_label']} ({ex['max_severity']}/5)",
            "",
            "### Severity breakdown",
            "",
        ]
        lines.extend(
            _md_table(
                ["Severity", "Events", "Color"],
                [
                    (label, count, severity_color(i + 1))
                    for i, (label, count) in enumerate(ex["severity_breakdown"])
                ],
            )
        )
        lines += ["", "## 2. Key Statistics", ""]
        lines.extend(_md_table(["Metric", "Value"], data["key_statistics"]))
        lines += ["", "## 3. Event Breakdown by Type", ""]

        if data["events_by_type"]:
            lines.extend(
                _md_table(
                    ["Crisis type", "Events", "Share", "Affected", "Casualties"],
                    data["events_by_type"],
                )
            )
        else:
            lines.append("No crisis events were recorded in the selected window.")

        lines += ["", "## 4. Regional Risk Assessment", ""]
        map_preview = self.create_map_placeholder(region)
        lines.extend(
            [line if not line.startswith("#") else line.lstrip("#").strip()
             for line in map_preview.splitlines()]
        )
        lines += ["", "### Risk hotspots", ""]
        if data["regional_risk"]:
            lines.extend(
                _md_table(
                    ["Area", "Events", "Dominant type", "Avg severity", "Max severity", "Risk"],
                    data["regional_risk"],
                )
            )
        else:
            lines.append("No significant risk clusters were detected in this window.")

        lines += ["", "## 5. ML-Powered Predictions", ""]
        pred = data["predictions"]
        for narrative_line in pred["narrative"]:
            lines.append(f"- {narrative_line}")
        if pred["rows"]:
            lines += [""] + _md_table(
                ["Region", "Crisis type", "Forecast date", "Predicted events", "95% CI", "Model"],
                pred["rows"],
            )

        lines += ["", "## 6. Trend Analysis", ""]
        trend = data["trend"]
        lines.extend(
            [
                f"- **Peak day:** {trend['peak_day'] or 'n/a'} "
                f"({trend['peak_count']} events)",
                f"- **Direction:** {trend['direction']} "
                f"(first half avg {trend['first_half_avg']:.1f} vs second half avg "
                f"{trend['second_half_avg']:.1f} events/day)",
                f"- **Average events/day:** {trend['avg_per_day']:.1f}",
                f"- **Change second-to-first half:** "
                f"{'+' if (trend['change_pct'] or 0) > 0 else ''}"
                f"{(trend['change_pct'] or 0):.1f}%",
            ]
        )

        lines += ["", "## 7. Recommended Actions", ""]
        lines.append(f"*Priority set by peak severity "
                     f"({ex['max_severity_label']}, severity {ex['max_severity']}/5).*")
        for idx, action in enumerate(data["recommended_actions"], start=1):
            lines.append(f"{idx}. {action}")

        lines += [
            "",
            "---",
            "",
            "_This report was generated automatically by CrisisWatch AI. "
            "ML forecasts are statistical estimates and should be validated by "
            "ground-truth reporting before operational use._",
        ]
        return "\n".join(lines).strip() + "\n"

    def to_html(self, markdown_content: str) -> str:
        """Convert a Markdown report into a self-contained HTML document."""
        if not markdown_content or not markdown_content.strip():
            raise ValueError("markdown_content must not be empty")

        title = "CrisisWatch AI Report"
        first_line = markdown_content.splitlines()[0].lstrip("#").strip() if markdown_content.splitlines() else ""
        if first_line:
            title = first_line

        body = _md_to_html(markdown_content)
        page_title = html_escape(title)
        return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{page_title}</title>
<style>
    body {{ font-family: -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
           max-width: 900px; margin: 0 auto; padding: 32px 24px;
           color: #1a202c; line-height: 1.55; }}
    h1 {{ border-bottom: 3px solid #1a73e8; padding-bottom: 8px; }}
    h2 {{ color: #1a73e8; border-bottom: 1px solid #e2e8f0;
          padding-bottom: 4px; margin-top: 30px; }}
    h3 {{ margin-top: 22px; }}
    table {{ border-collapse: collapse; width: 100%; margin: 14px 0;
            font-size: 14px; }}
    th, td {{ border: 1px solid #cbd5e1; padding: 6px 10px; text-align: left; }}
    th {{ background: #1a73e8; color: #ffffff; }}
    tr:nth-child(even) td {{ background: #f1f5f9; }}
    code, pre {{ font-family: 'SFMono-Regular', Consolas, monospace;
                background: #f8fafc; font-size: 13px; }}
    blockquote {{ border-left: 4px solid #94a3b8; margin-left: 0;
                 padding-left: 14px; color: #475569; }}
    hr {{ border: none; border-top: 1px solid #e2e8f0; margin: 26px 0; }}
    @media print {{ body {{ padding: 0; }} }}
</style>
</head>
<body>
{body}
</body>
</html>
"""

    def generate_pdf(self, html_content: str, output_path: str) -> str:
        """Generate a PDF document from HTML content using ReportLab.

        Args:
            html_content: The HTML produced by :meth:`to_html`.
            output_path: Destination path for the generated PDF file.

        Returns:
            The absolute ``output_path`` of the written PDF.

        Raises:
            ValueError: If ``html_content`` is empty.
        """
        if not html_content or not html_content.strip():
            raise ValueError("html_content must not be empty")

        if _REPORTLAB_MISSING:
            raise RuntimeError(
                "reportlab is required for PDF generation; install it via "
                "'pip install reportlab'."
            )

        output_dir = os.path.dirname(os.path.abspath(output_path))
        os.makedirs(output_dir, exist_ok=True)

        parser = _HtmlPdfParser(page_width=A4[0])
        parser.feed(html_content)
        parser.close()

        if not parser.flowables:
            raise ValueError("No reportable content found in the supplied HTML")

        doc = SimpleDocTemplate(
            output_path,
            pagesize=A4,
            leftMargin=54,
            rightMargin=54,
            topMargin=56,
            bottomMargin=56,
            title="CrisisWatch AI Situation Report",
            author="CrisisWatch AI",
        )
        doc.build(parser.flowables, onFirstPage=_pdf_footer, onLaterPages=_pdf_footer)
        return os.path.abspath(output_path)

    def create_map_placeholder(self, region: str) -> str:
        """Create a static map description/summary for a region.

        Interactive geospatial layers are not embeddable in static reports, so
        this returns a concise stand-in: the covered area plus a severity
        legend that lets readers map report tables onto a real map.

        Args:
            region: The geographic region the report covers.

        Returns:
            A short Markdown block describing the map placeholder.
        """
        region = region or "Global"
        legend = ", ".join(
            f"{severity_label(i)} ({severity_color(i)})" for i in range(1, 6)
        )
        return (
            f"#### Map Preview — {region}\n\n"
            f"An interactive geospatial map for **{region}** is available on the "
            f"live dashboard; static reports include only a text summary of the "
            f"leading risk hotspots (see table below).\n\n"
            f"**Severity legend:** {legend}."
        )

    # ------------------------------------------------------------------ #
    # Report data aggregation
    # ------------------------------------------------------------------ #
    def _build_report_data(
        self,
        region: str,
        date_from: Any,
        date_to: Any,
        crises_data: Sequence[dict[str, Any]],
        forecasts_data: Sequence[dict[str, Any]],
        clusters_data: Sequence[dict[str, Any]],
    ) -> dict[str, Any]:
        """Aggregate raw inputs into a structured report payload."""
        from_dt = _to_datetime(date_from)
        to_dt = _to_datetime(date_to)

        crises = [c for c in crises_data if isinstance(c, dict)]
        forecasts = [f for f in forecasts_data if isinstance(f, dict)]
        clusters = [c for c in clusters_data if isinstance(c, dict)]

        total_affected = 0
        total_casualties = 0
        total_displaced = 0
        countries: set[str] = set()
        daily_counts: Counter[str] = Counter()
        severity_counter: Counter[int] = Counter()
        type_counts: Counter[str] = Counter()
        type_affected: Counter[str] = Counter()
        type_casualties: Counter[str] = Counter()

        for crisis in crises:
            severity = _severity_of(crisis)
            event_type = _event_type_label(crisis)
            country = str(_field(crisis, "country") or _field(crisis, "region") or "Unknown")
            countries.add(country)

            affected = int(_field(crisis, "affected") or 0)
            casualties = int(_field(crisis, "casualties") or 0)
            displaced = int(_field(crisis, "displaced") or 0)
            if affected == 0:
                affected = casualties + displaced

            total_affected += affected
            total_casualties += casualties
            total_displaced += displaced
            severity_counter[severity] += 1
            type_counts[event_type] += 1
            type_affected[event_type] += affected
            type_casualties[event_type] += casualties

            event_ts = crisis.get("timestamp")
            if event_ts is not None:  # pragma: no branch
                try:
                    daily_counts[_format_date(_to_datetime(event_ts))] += 1
                except (TypeError, ValueError):
                    continue

        # ----- Executive summary -------------------------------------- #
        total_events = len(crises)
        max_severity = max(severity_counter) if severity_counter else 1
        avg_severity = (
            mean([_severity_of(c) for c in crises]) if crises else 0.0
        )
        severity_breakdown = [
            (severity_label(i), severity_counter.get(i, 0)) for i in range(1, 6)
        ]

        # ----- Key statistics ----------------------------------------- #
        peak_day, peak_count = (
            max(daily_counts.items(), key=lambda kv: kv[1])
            if daily_counts else ("", 0)
        )
        risk_areas = self._regional_risk_rows(clusters, crises)
        key_statistics = [
            ("Events reported", total_events),
            ("Countries / areas affected", len(countries)),
            ("Total people affected", f"{total_affected:,}"),
            ("Confirmed casualties", f"{total_casualties:,}"),
            ("People displaced", f"{total_displaced:,}"),
            ("Average severity", f"{avg_severity:.1f}/5"),
            ("Peak day", f"{peak_day or 'n/a'} ({peak_count} events)"),
            ("Active risk areas", len(risk_areas)),
        ]

        # ----- Events by type ----------------------------------------- #
        events_by_type = []
        for event_type, count in type_counts.most_common():
            share = (count / total_events * 100.0) if total_events else 0.0
            events_by_type.append(
                (
                    event_type,
                    count,
                    f"{share:.1f}%",
                    type_affected.get(event_type, 0),
                    type_casualties.get(event_type, 0),
                )
            )

        # ----- Regional risk ------------------------------------------ #
        regional_risk = []
        for area, events, dominant, avg_sev, max_sev, risk in risk_areas:
            regional_risk.append(
                (area, events, dominant, f"{avg_sev:.1f}", max_sev, f"{risk:.2f}")
            )
        regional_risk.sort(key=lambda row: float(row[5]), reverse=True)

        # ----- Predictions -------------------------------------------- #
        forecast_rows, forecast_narrative, model_versions = self._prediction_rows(
            region, forecasts
        )

        # ----- Trend analysis ----------------------------------------- #
        trend = self._trend_analysis(daily_counts)

        # ----- Recommended actions ------------------------------------ #
        rationale, actions = _ACTION_TEMPLATES[max_severity]
        recommended_actions = _UNIVERSAL_ACTIONS + actions

        return {
            "region": region,
            "date_from_label": _format_date(from_dt),
            "date_to_label": _format_date(to_dt),
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
            "executive_summary": {
                "total_events": total_events,
                "total_affected": total_affected,
                "total_casualties": total_casualties,
                "total_displaced": total_displaced,
                "countries_count": len(countries),
                "max_severity": max_severity,
                "max_severity_label": severity_label(max_severity),
                "avg_severity": avg_severity,
                "severity_breakdown": severity_breakdown,
                "rationale": rationale,
            },
            "key_statistics": key_statistics,
            "events_by_type": events_by_type,
            "regional_risk": regional_risk,
            "predictions": {
                "narrative": forecast_narrative,
                "rows": forecast_rows,
                "model_versions": model_versions,
            },
            "trend": trend,
            "recommended_actions": recommended_actions,
        }

    def _regional_risk_rows(
        self,
        clusters: Sequence[dict[str, Any]],
        crises: Sequence[dict[str, Any]],
    ) -> list[tuple[str, int, str, float, int, float]]:
        """Derive risk hotspot rows from clusters, falling back to country data."""
        rows: list[tuple[str, int, str, float, int, float]] = []

        def risk_score(avg_sev: float, event_count: int) -> float:
            return round(float(avg_sev) * log1p(max(event_count, 0)), 2)

        for cluster in clusters:
            label = (
                _field(cluster, "label")
                or _field(cluster, "cluster")
                or _field(cluster, "region")
                or str(_field(cluster, "center", "Risk Area"))
            )
            events = int(_field(cluster, "size") or _field(cluster, "event_count") or 0)
            avg_sev = _severity_of(cluster)
            max_sev = max(
                int(_field(cluster, "max_severity", avg_sev)), avg_sev
            )
            dominant = str(
                _field(cluster, "dominant_type")
                or _field(cluster, "primary_type")
                or "Mixed / unknown"
            ).replace("_", " ").title()
            risk = _field(cluster, "risk_score")
            if risk is None:
                risk = risk_score(avg_sev, events)
            rows.append((str(label).replace("_", " ").title(), events, dominant,
                         float(avg_sev), max_sev, float(risk)))

        if rows:
            return rows

        # Fallback: aggregate crises by country/area.
        groups: dict[str, list[dict[str, Any]]] = {}
        for crisis in crises:
            area = str(
                _field(crisis, "country")
                or _field(crisis, "region")
                or "Unknown"
            )
            groups.setdefault(area, []).append(crisis)

        for area, group in groups.items():
            count = len(group)
            sevs = [_severity_of(c) for c in group]
            avg_sev = mean(sevs)
            dominant = self._dominant_type(group)
            rows.append(
                (area, count, dominant, float(avg_sev), max(sevs),
                 risk_score(avg_sev, count))
            )
        rows.sort(key=lambda r: r[5], reverse=True)
        return rows

    @staticmethod
    def _dominant_type(group: Sequence[dict[str, Any]]) -> str:
        """Return the most frequent crisis type label within a group."""
        counts: Counter[str] = Counter(_event_type_label(c) for c in group)
        most_common = counts.most_common(1)
        return most_common[0][0] if most_common else "Mixed / unknown"

    def _prediction_rows(
        self,
        region: str,
        forecasts: Sequence[dict[str, Any]],
    ) -> tuple[list[tuple[str, str, str, str, str, str]], list[str], set[str]]:
        """Normalize ML forecast rows and build the narrative summary."""
        rows: list[tuple[str, str, str, str, str, str]] = []
        model_versions: set[str] = set()
        narrative: list[str] = []

        for forecast in forecasts:
            region_name = str(_field(forecast, "region") or region or "Global")
            crisis_type = str(_field(forecast, "crisis_type", "unknown")).replace("_", " ").title()
            model_version = str(_field(forecast, "model_version", "unknown"))
            model_versions.add(model_version)
            try:
                forecast_date = _format_date(_to_datetime(forecast.get("forecast_date")))
            except (TypeError, ValueError):
                forecast_date = str(_field(forecast, "forecast_date", "n/a"))

            predicted = float(_field(forecast, "predicted_count", 0.0))
            low = float(_field(forecast, "confidence_lower", predicted))
            high = float(_field(forecast, "confidence_upper", predicted))
            rows.append(
                (
                    region_name,
                    crisis_type,
                    forecast_date,
                    f"{predicted:.1f}",
                    f"{low:.1f} - {high:.1f}",
                    model_version,
                )
            )

        rows.sort(key=lambda r: r[2])
        if rows:
            top = max(rows, key=lambda r: float(r[3]))
            total_predicted = sum(float(r[3]) for r in rows)
            narrative.append(
                f"Highest model expectation is {top[3]} predicted events for "
                f"**{top[1]}** in **{top[0]}** on {top[2]} "
                f"(model {top[5]})."
            )
            narrative.append(
                f"Forecasts cover {len(rows)} prediction(s) totaling "
                f"~{total_predicted:.0f} expected events across the window. "
                f"Models in use: {', '.join(sorted(model_versions)) or 'various'}."
            )
            narrative.append(
                "Forecast confidence intervals widen with distance from the "
                "observation window; treat predictions >14 days out as directional."
            )
        else:
            narrative.append(
                "No ML forecasts are available for the selected window. "
                "Enable forecasting sources so the models can estimate "
                "near-term escalation risk."
            )
        return rows, narrative, model_versions

    @staticmethod
    def _trend_analysis(daily_counts: Counter[str]) -> dict[str, Any]:
        """Compute basic daily-event trend metrics."""
        if not daily_counts:
            return {
                "peak_day": "",
                "peak_count": 0,
                "direction": "No data",
                "first_half_avg": 0.0,
                "second_half_avg": 0.0,
                "avg_per_day": 0.0,
                "change_pct": None,
            }

        ordered_days = sorted(daily_counts)
        counts = [daily_counts[day] for day in ordered_days]
        peak_day, peak_count = max(daily_counts.items(), key=lambda kv: kv[1])

        total_days = max(len(ordered_days), 1)
        split = (len(counts) + 1) // 2
        first_half = counts[:split]
        second_half = counts[split:]
        first_avg = mean(first_half) if first_half else 0.0
        second_avg = mean(second_half) if second_half else first_avg

        change_pct: float | None = None
        if first_avg:
            change_pct = (second_avg - first_avg) / first_avg * 100.0

        if first_half and second_half:
            if change_pct is not None and change_pct > 5.0:
                direction = "Rising"
            elif change_pct is not None and change_pct < -5.0:
                direction = "Falling"
            else:
                direction = "Stable"
        else:
            direction = "Stable (insufficient range)"

        return {
            "peak_day": peak_day,
            "peak_count": int(peak_count),
            "direction": direction,
            "first_half_avg": first_avg,
            "second_half_avg": second_avg,
            "avg_per_day": sum(counts) / total_days,
            "change_pct": change_pct,
        }


# --------------------------------------------------------------------------- #
# HTML -> PDF rendering (ReportLab)
# --------------------------------------------------------------------------- #

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import (
        HRFlowable,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )
except ImportError:  # pragma: no cover - reportlab ships in requirements.txt
    _REPORTLAB_MISSING = True
else:
    _REPORTLAB_MISSING = False


def _md_to_html(markdown_content: str) -> str:
    """Convert Markdown text to an HTML fragment using the ``markdown`` lib."""
    import markdown

    return markdown.markdown(
        markdown_content,
        extensions=["tables", "fenced_code", "sane_lists"],
        output_format="html5",
    )


def _pdf_footer(canvas, doc) -> None:  # type: ignore[no-untyped-def]
    """Draw a page footer with branding and the page number."""
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.grey)
    canvas.drawString(54, 30, "CrisisWatch AI — Intelligence Report")
    canvas.drawRightString(A4[0] - 54, 30, f"Page {doc.page}")
    canvas.restoreState()


class _HtmlPdfParser(HTMLParser):
    """Convert the subset of HTML produced by :meth:`to_html` into flowables.

    Supports headings, paragraphs, bullet lists, order lists, tables, code
    blocks, and inline emphasis — everything the report renderer emits.
    """

    _SKIP_TAGS = {"head", "style", "script", "title"}
    _IGNORED_TAGS = {"html", "body", "thead", "tbody", "form", "input"}
    _INLINE_OPEN = {"b": "<b>", "strong": "<b>", "i": "<i>", "em": "<i>", "u": "<u>", "code": "<font name='Courier'>"}
    _INLINE_CLOSE = {"b": "</b>", "strong": "</b>", "i": "</i>", "em": "</i>", "u": "</u>", "code": "</font>"}

    def __init__(self, page_width: float) -> None:
        super().__init__(convert_charrefs=True)
        self.page_width = page_width
        self.flowables: list[Any] = []

        self._stack: list[tuple[str, dict[str, Any]]] = []
        self._text: list[str] = []
        self._skip_depth = 0
        self._lists: list[tuple[bool, int]] = []
        self._table: list[list[tuple[bool, str]]] | None = None
        self._row: list[tuple[bool, str]] | None = None

        self.base_style = ParagraphStyle(
            name="ReportBody", fontName="Helvetica", fontSize=9.5,
            leading=13, spaceBefore=3, spaceAfter=6,
        )
        self.h1 = ParagraphStyle(
            name="ReportH1", parent=self.base_style, fontName="Helvetica-Bold",
            fontSize=16, leading=20, spaceBefore=6, spaceAfter=10,
            textColor=colors.HexColor("#1a73e8"),
        )
        self.h2 = ParagraphStyle(
            name="ReportH2", parent=self.base_style, fontName="Helvetica-Bold",
            fontSize=13, leading=16, spaceBefore=16, spaceAfter=6,
            textColor=colors.HexColor("#1a73e8"),
        )
        self.h3 = ParagraphStyle(
            name="ReportH3", parent=self.base_style, fontName="Helvetica-Bold",
            fontSize=11.5, leading=14, spaceBefore=12, spaceAfter=4,
        )
        self.h4 = ParagraphStyle(
            name="ReportH4", parent=self.base_style, fontName="Helvetica-Bold",
            fontSize=10.5, leading=13, spaceBefore=10, spaceAfter=3,
        )
        self.bullet = ParagraphStyle(
            name="ReportBullet", parent=self.base_style, leftIndent=16,
            bulletIndent=4,
        )
        self.code_style = ParagraphStyle(
            name="ReportCode", parent=self.base_style, fontName="Courier",
            fontSize=8.5, leading=11, backColor=colors.HexColor("#f8fafc"),
            borderPadding=6,
        )
        self.cell = ParagraphStyle(
            name="ReportCell", parent=self.base_style, fontSize=8.5,
            leading=11, spaceBefore=0, spaceAfter=0,
        )
        self.cell_header = ParagraphStyle(
            name="ReportCellHeader", parent=self.cell, fontName="Helvetica-Bold",
            textColor=colors.white,
        )

    # -- HTMLParser hooks ------------------------------------------------ #
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:  # type: ignore[override]
        tag = tag.lower()
        if tag in self._IGNORED_TAGS:
            return
        if tag in self._SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return

        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._finalize_current()
            self._stack.append(("heading", {"level": int(tag[1])}))
            self._text = []
        elif tag == "p":
            self._finalize_current()
            self._stack.append(("p", {}))
            self._text = []
        elif tag == "ul":
            self._lists.append((False, 0))
        elif tag == "ol":
            self._lists.append((True, 0))
        elif tag == "li":
            self._finalize_current()
            number = 0
            if self._lists:
                ordered, count = self._lists[-1]
                if ordered:
                    number = count + 1
                    self._lists[-1] = (True, number)
            self._stack.append(("li", {"number": number}))
            self._text = []
        elif tag == "pre":
            self._finalize_current()
            self._stack.append(("pre", {}))
            self._text = []
        elif tag == "table":
            self._finalize_current()
            self._table = []
        elif tag == "tr":
            if self._table is not None:
                self._row = []
        elif tag in ("td", "th"):
            self._finalize_current()
            self._stack.append(("cell", {"header": tag == "th"}))
            self._text = []
        elif tag == "br":
            if self._stack:
                self._text.append("<br/>")
        elif tag == "hr":
            self._finalize_current()
            self.flowables.append(
                HRFlowable(width="100%", thickness=0.7, color=colors.grey,
                           spaceBefore=8, spaceAfter=8)
            )
        elif tag in self._INLINE_OPEN:
            self._text.append(self._INLINE_OPEN[tag])

    def handle_endtag(self, tag: str) -> None:  # type: ignore[override]
        tag = tag.lower()
        if tag in self._IGNORED_TAGS:
            return
        if tag in self._SKIP_TAGS:
            if self._skip_depth:
                self._skip_depth -= 1
            return
        if self._skip_depth:
            return

        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            if self._stack and self._stack[-1][0] == "heading":
                self._finalize_current()
        elif tag == "p":
            if self._stack and self._stack[-1][0] == "p":
                self._finalize_current()
        elif tag == "li":
            if self._stack and self._stack[-1][0] == "li":
                self._finalize_current()
        elif tag in ("ul", "ol"):
            if self._lists:
                self._lists.pop()
        elif tag == "pre":
            if self._stack and self._stack[-1][0] == "pre":
                self._finalize_current()
        elif tag == "table":
            self._table = self._table or []
            if self._row is not None:
                self._table.append(self._row)
                self._row = None
            self._emit_table()
            self._table = None
        elif tag == "tr":
            if self._table is not None and self._row is not None:
                self._table.append(self._row)
                self._row = None
        elif tag in ("td", "th"):
            if self._stack and self._stack[-1][0] == "cell":
                header = bool(self._stack[-1][1].get("header", False))
                content = "".join(self._text).strip()
                self._stack.pop()
                self._text = []
                if self._row is not None:
                    self._row.append((header, content))
        elif tag in self._INLINE_CLOSE and not self._in_container("pre"):
                self._text.append(self._INLINE_CLOSE[tag])

    def handle_data(self, data: str) -> None:  # type: ignore[override]
        if self._skip_depth:
            return
        if self._stack:
            self._text.append(html_escape(data, quote=False))

    # -- Helpers ---------------------------------------------------------- #
    def _current_kind(self) -> str | None:
        return self._stack[-1][0] if self._stack else None

    def _in_container(self, kind: str) -> bool:
        return any(kind == k for k, _ in self._stack)

    def _finalize_current(self) -> None:
        """Pop the current block container and append its flowable."""
        if not self._stack:
            self._text = []
            return
        kind, kw = self._stack.pop()
        content = "".join(self._text).strip()
        self._text = []

        if not content:
            return

        if kind == "heading":
            level = min(max(kw.get("level", 2), 1), 4)
            style = {1: self.h1, 2: self.h2, 3: self.h3, 4: self.h4}[level]
            self.flowables.append(Paragraph(content, style))
        elif kind == "p":
            self.flowables.append(Paragraph(content, self.base_style))
        elif kind == "li":
            number = kw.get("number", 0)
            bullet = f"{number}." if number else "\u2022"
            self.flowables.append(Paragraph(content, self.bullet, bulletText=bullet))
        elif kind == "pre":
            self.flowables.append(Paragraph(content, self.code_style))
        elif kind == "cell":
            header = kw.get("header", False)
            if self._row is not None:
                self._row.append((header, content))

    def _emit_table(self) -> None:
        """Turn the collected ``(is_header, text)`` rows into a styled table."""
        rows = self._table or []
        if not rows:
            return

        col_count = max(len(row) for row in rows)
        col_width = (self.page_width - 108) / max(col_count, 1)
        data: list[list[Paragraph]] = []
        for row in rows:
            cells: list[Paragraph] = []
            for idx in range(col_count):
                header, text = row[idx] if idx < len(row) else (False, "")
                style = self.cell_header if header else self.cell
                cells.append(Paragraph(text or " ", style))
            data.append(cells)

        table = Table(data, colWidths=[col_width] * col_count, repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a73e8")),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        self.flowables.append(Spacer(1, 8))
        self.flowables.append(table)
        self.flowables.append(Spacer(1, 8))