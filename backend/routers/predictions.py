"""ML predictions router — severity, NLP classification, forecasts, clusters, SHAP."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_db
from db.models import CrisisEvent, Prediction
from ml.classifier import CrisisClassifier
from ml.clustering import CrisisClustering
from ml.explainability import ModelExplainer, natural_language_explanation
from ml.forecaster import CrisisForecaster, aggregate_crises
from ml.nlp_classifier import NLPCrisisClassifier

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["predictions"])

SEVERITY_LEVELS = ["LOW", "MODERATE", "HIGH", "CRITICAL", "CATASTROPHIC"]


class SeverityRequest(BaseModel):
    event_type: str = Field(..., description="One of the supported crisis types")
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    population_density_estimate: float = Field(0.0, ge=0)
    historical_frequency_in_region: float = Field(0.0, ge=0)
    source_reliability_score: float = Field(0.8, ge=0, le=1)
    temperature: float = Field(25.0)
    wind_speed: float = Field(10.0)
    precipitation: float = Field(5.0)
    month: int | None = Field(None, ge=1, le=12)
    day_of_week: int | None = Field(None, ge=0, le=6)


class ClassifyRequest(BaseModel):
    text: str = Field(..., min_length=3, max_length=8000)


class ForecastRequest(BaseModel):
    region: str
    crisis_type: str | None = None
    periods: int = Field(30, ge=1, le=365)
    freq: str = "D"


def _event_to_features(e: CrisisEvent, source_weight: float = 0.8) -> dict[str, Any]:
    return {
        "event_type": e.event_type.value,
        "latitude": e.latitude,
        "longitude": e.longitude,
        "population_density_estimate": 500.0,
        "historical_frequency_in_region": 3.0,
        "source_reliability_score": source_weight,
        "temperature": 25.0,
        "wind_speed": 10.0,
        "precipitation": 5.0,
        "month": e.timestamp.month if e.timestamp else None,
        "day_of_week": e.timestamp.weekday() if e.timestamp else None,
    }


def _load_classifier() -> CrisisClassifier:
    try:
        model = CrisisClassifier()
        model.load_model()
        if model.pipeline is None:
            raise RuntimeError("classifier model not loaded")
        return model
    except Exception as exc:  # noqa: BLE001
        logger.warning("Classifier unavailable (%s); training a fresh one.", exc)
        model = CrisisClassifier()
        model.train(save=True)
        return model


def _load_forecaster() -> CrisisForecaster:
    try:
        fc = CrisisForecaster()
        fc.load_model()
        if fc.model is None:
            raise RuntimeError("forecaster model not loaded")
        return fc
    except Exception as exc:  # noqa: BLE001
        logger.warning("Forecaster unavailable (%s).", exc)
        return CrisisForecaster()


def _load_nlp() -> NLPCrisisClassifier:
    try:
        model = NLPCrisisClassifier()
        model.load_model()
        return model
    except Exception as exc:  # noqa: BLE001
        logger.warning("NLP classifier unavailable (%s); using fallback.", exc)
        return NLPCrisisClassifier()


# --------------------------------------------------------------------------- #
# Severity prediction + SHAP explanation
# --------------------------------------------------------------------------- #


@router.post("/predict/severity", summary="Predict crisis severity with SHAP explanation")
async def predict_severity(req: SeverityRequest, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    model = await asyncio.to_thread(_load_classifier)
    features = req.model_dump()
    if features["month"] is None:
        features["month"] = datetime.now(timezone.utc).month
    if features["day_of_week"] is None:
        features["day_of_week"] = datetime.now(timezone.utc).weekday()

    def run() -> dict[str, Any]:
        result = model.predict(features)
        explainer = ModelExplainer()
        shap_top = explainer.explain(model.pipeline, features, feature_names=None)
        explanation_text = natural_language_explanation(shap_top)
        return {"result": result, "shap": shap_top, "explanation": explanation_text}

    out = await asyncio.to_thread(run)
    result: dict[str, Any] = out["result"] if isinstance(out["result"], dict) else {"severity": int(out["result"])}
    severity = int(result.get("severity", 3))

    record = Prediction(
        prediction_type="severity",
        predicted_value={"event_type": req.event_type, "severity": severity},
        confidence=float(result.get("confidence", 0.5)),
        shap_values=out["shap"],
        model_version="xgb-v1",
    )
    db.add(record)
    await db.commit()

    return {
        "prediction": {
            "severity": severity,
            "severity_label": SEVERITY_LEVELS[severity - 1],
            "confidence": result.get("confidence"),
            "probabilities": result.get("probabilities"),
        },
        "shap_values": out["shap"],
        "explanation": out["explanation"],
        "model": "XGBoost (RandomizedSearchCV-tuned)",
        "prediction_id": record.id,
    }


# --------------------------------------------------------------------------- #
# NLP text classification
# --------------------------------------------------------------------------- #


@router.post("/predict/classify", summary="Classify crisis report text (NLP)")
async def classify_text(req: ClassifyRequest, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    model = await asyncio.to_thread(_load_nlp)
    result = await asyncio.to_thread(model.predict, req.text)
    labels = result["labels"]
    scores = result["scores"]

    record = Prediction(
        prediction_type="nlp_classification",
        predicted_value={"labels": labels, "scores": scores[:5]},
        confidence=max(scores) if scores else 0.0,
        model_version="distilbert-base-uncased-finetuned",
    )
    db.add(record)
    await db.commit()

    return {
        "text": req.text[:200],
        "labels": labels,
        "scores": scores,
        "primary_label": labels[0],
        "primary_score": scores[0],
        "model": "DistilBERT fine-tuned (multi-label)",
        "prediction_id": record.id,
    }


# --------------------------------------------------------------------------- #
# Time-series forecasting
# --------------------------------------------------------------------------- #


@router.get("/forecast", summary="Time-series forecast for a region")
async def forecast_for_region(
    region: str = Query(..., description="Region name"),
    crisis_type: str | None = Query(None),
    periods: int = Query(60, ge=1, le=365),
    freq: str = Query("W", pattern="^(D|W|MS)$"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    stmt = select(CrisisEvent).where(CrisisEvent.region == region)
    if crisis_type:
        stmt = stmt.where(CrisisEvent.event_type == crisis_type.replace("_", ""))
    rows = await db.execute(stmt)
    events = rows.scalars().all()
    if not events:
        raise HTTPException(status_code=404, detail=f"No crisis events found for region '{region}'")

    df = pd.DataFrame(
        [
            {
                "date": e.timestamp,
                "type": e.event_type.value,
                "severity": e.severity,
            }
            for e in events
        ]
    )
    series = aggregate_crises(df, group_by="type", freq="D")
    if crisis_type:
        series = series[series.group == crisis_type]
        if series.empty:
            series = aggregate_crises(df, group_by="total", freq="D")

    def train_and_predict() -> dict[str, Any]:
        fc = CrisisForecaster()
        groups = [("all", series)]
        if "group" in series.columns:
            groups = [(gname, gdf) for gname, gdf in series.groupby("group")]
        all_frames: list[dict[str, Any]] = []
        metrics: dict[str, Any] = {}
        for gname, gdf in groups:
            try:
                fc.train(gdf[["ds", "y"]])
                pred = fc.predict(periods=periods, freq=freq)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Forecast failed for %s: %s", gname, exc)
                continue
            dates = pred["ds"]
            frames = [
                {
                    "ds": d.isoformat(),
                    "yhat": float(y),
                    "yhat_lower": float(yl),
                    "yhat_upper": float(yu),
                    "group": str(gname),
                }
                for d, y, yl, yu in zip(dates, pred["yhat"], pred["yhat_lower"], pred["yhat_upper"], strict=False)
            ]
            all_frames.extend(frames)
            try:
                cv = fc.cross_validate(n_splits=3)
                metrics[str(gname)] = cv
            except Exception:  # noqa: BLE001
                pass
        return {"points": all_frames, "metrics": metrics}

    result = {}
    try:
        result = await asyncio.to_thread(train_and_predict)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Forecast computation failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "region": region,
        "crisis_type": crisis_type or "all",
        "periods": periods,
        "freq": freq,
        "model": "Prophet (yearly + weekly seasonality)",
        "points": result.get("points", []),
        "metrics": result.get("metrics", {}),
    }


# --------------------------------------------------------------------------- #
# Spatial clustering / hotspots
# --------------------------------------------------------------------------- #


@router.get("/clusters", summary="Current crisis clusters/hotspots")
async def crisis_clusters(
    region: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    stmt = select(CrisisEvent)
    if region:
        stmt = stmt.where(CrisisEvent.region == region)
    rows = await db.execute(stmt)
    events = rows.scalars().all()
    if not events:
        raise HTTPException(status_code=404, detail="No crisis events to cluster")

    df = pd.DataFrame(
        [
            {
                "latitude": e.latitude,
                "longitude": e.longitude,
                "severity": e.severity,
                "event_type": e.event_type.value,
            }
            for e in events
        ]
    )

    def run() -> list[dict[str, Any]]:
        clustering = CrisisClustering()
        clustering.fit_predict(df)
        return clustering.get_hotspots()

    hotspots = await asyncio.to_thread(run)
    return {"clusters": hotspots, "count": len(hotspots), "model": "HDBSCAN"}


# --------------------------------------------------------------------------- #
# Model metadata + demo forecast sync
# --------------------------------------------------------------------------- #


@router.get("/models", summary="List available ML models and their status")
async def model_info() -> dict[str, Any]:
    classifier = _load_classifier()
    nlp = _load_nlp()
    return {
        "severity_classifier": {
            "name": "XGBoost Crisis Severity Classifier",
            "loaded": classifier.pipeline is not None,
            "classes": SEVERITY_LEVELS,
            "version": "xgb-v1",
        },
        "nlp_classifier": {
            "name": "DistilBERT Multi-Label Text Classifier",
            "loaded": nlp.model is not None,
            "labels": nlp.labels if hasattr(nlp, "labels") else [],
            "version": "distilbert-base-uncased-finetuned",
        },
        "forecaster": {
            "name": "Prophet Time-Series Forecaster",
            "loaded": _load_forecaster().model is not None,
        },
        "clustering": {"name": "HDBSCAN Spatial Hotspot Identifier"},
        "explainability": {"name": "SHAP TreeExplainer"},
    }