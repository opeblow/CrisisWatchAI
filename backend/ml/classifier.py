"""Crisis severity classifier powered by XGBoost.

Given a curated set of structured features for a crisis event, this module predicts
a five-point severity rating:

    1 = Low
    2 = Medium
    3 = High
    4 = Critical
    5 = Catastrophic

The model is a scikit-learn ``Pipeline`` built with a ``ColumnTransformer``
(``StandardScaler`` for numeric features, ``OneHotEncoder`` for categorical
features, e.g. ``event_type``) followed by an ``XGBClassifier``.  Hyper-parameters
are tuned with ``RandomizedSearchCV`` using a stratified 70/15/15
train/validation/test split.

When no training data is available, :func:`generate_synthetic_data` produces a
realistic demo dataset so the pipeline can be exercised end-to-end.

Typical usage::

    from backend.ml.classifier import CrisisClassifier

    clf = CrisisClassifier()
    result = clf.train()                 # trains on generated synthetic data
    prediction = clf.predict({
        "event_type": "earthquake",
        "latitude": 37.77,
        "longitude": -122.41,
        "population_density_estimate": 1800.0,
        "historical_frequency_in_region": 0.7,
        "temperature": 18.0,
        "wind_speed": 12.0,
        "precipitation": 5.0,
        "month": 4,
        "day_of_week": 2,
        "source_reliability_score": 0.9,
    })
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from scipy.stats import randint, uniform
from sklearn.compose import ColumnTransformer
from sklearn.metrics import classification_report, confusion_matrix, f1_score
from sklearn.model_selection import RandomizedSearchCV, StratifiedShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from xgboost import XGBClassifier

logger = logging.getLogger(__name__)

SEVERITY_LEVELS: list[int] = [1, 2, 3, 4, 5]
SEVERITY_NAMES: dict[int, str] = {
    1: "Low",
    2: "Medium",
    3: "High",
    4: "Critical",
    5: "Catastrophic",
}

CATEGORICAL_FEATURES: list[str] = ["event_type"]
NUMERIC_FEATURES: list[str] = [
    "latitude",
    "longitude",
    "population_density_estimate",
    "historical_frequency_in_region",
    "temperature",
    "wind_speed",
    "precipitation",
    "month",
    "day_of_week",
    "source_reliability_score",
]
FEATURES: list[str] = CATEGORICAL_FEATURES + NUMERIC_FEATURES

EVENT_TYPES: list[str] = [
    "conflict",
    "flood",
    "earthquake",
    "epidemic",
    "drought",
    "cyclone",
    "food_crisis",
    "displacement",
]

MODEL_DIR: Path = Path(__file__).resolve().parent / "models"
MODEL_PATH: Path = MODEL_DIR / "crisis_classifier.joblib"

# (lat, lon, event_type, severity_bias) worlds hotspots used by the synthetic generator.
_SYNTH_HOTSPOTS: list[tuple[float, float, str, float]] = [
    (37.77, -122.41, "earthquake", 3.2),
    (23.74, 90.41, "flood", 3.4),
    (8.44, 115.20, "cyclone", 3.3),
    (-1.94, 29.87, "conflict", 3.6),
    (15.78, 32.55, "drought", 3.0),
    (6.11, -66.84, "epidemic", 3.1),
    (12.97, 77.59, "food_crisis", 2.9),
    (13.37, 103.19, "displacement", 3.0),
]

_PARAM_DISTRIBUTIONS: dict[str, Any] = {
    "clf__n_estimators": randint(100, 500),
    "clf__max_depth": randint(4, 12),
    "clf__learning_rate": uniform(0.01, 0.29),
    "clf__subsample": uniform(0.6, 0.4),
    "clf__colsample_bytree": uniform(0.6, 0.4),
    "clf__min_child_weight": randint(1, 10),
    "clf__gamma": uniform(0.0, 0.5),
}


def generate_synthetic_data(
    n_samples: int = 2500, random_state: int = 42
) -> tuple[pd.DataFrame, pd.Series]:
    """Generate a realistic synthetic dataset of crisis events.

    Events are drawn from a set of geographic hotspots (with a tunable degree of
    spatial noise) plus a worldwide uniform background.  Severity is computed from a
    weighted combination of the modulating factors so the learned model has a
    signal to exploit: event type, population density, historical frequency,
    weather conditions and source reliability.

    Returns
    -------
    (X, y)
        X is a ``DataFrame`` with the raw feature columns, y is a ``Series`` of
        severity int labels in ``[1, 5]``.
    """
    rng = np.random.default_rng(random_state)

    event_types = np.array(EVENT_TYPES)
    hotspot_types = np.array([h[2] for h in _SYNTH_HOTSPOTS])
    hotspot_lat = np.array([h[0] for h in _SYNTH_HOTSPOTS])
    hotspot_lon = np.array([h[1] for h in _SYNTH_HOTSPOTS])

    n_hotspot = int(n_samples * 0.7)
    n_random = n_samples - n_hotspot

    if n_hotspot > 0:
        hs_idx = rng.integers(0, len(_SYNTH_HOTSPOTS), size=n_hotspot)
        lat_hs = hotspot_lat[hs_idx] + rng.normal(0.0, 0.8, size=n_hotspot)
        lon_hs = hotspot_lon[hs_idx] + rng.normal(0.0, 0.8, size=n_hotspot)
        type_hs = hotspot_types[hs_idx]
    else:
        lat_hs, lon_hs, type_hs = (
            np.array([], dtype=float),
            np.array([], dtype=float),
            np.array([], dtype=object),
        )

    lat_ran = rng.uniform(-60.0, 70.0, size=n_random)
    lon_ran = rng.uniform(-180.0, 180.0, size=n_random)
    type_ran = rng.choice(event_types, size=n_random)

    lat = np.concatenate([lat_hs, lat_ran])
    lon = np.concatenate([lon_hs, lon_ran])
    types = np.concatenate([type_hs, type_ran])

    month = rng.integers(1, 13, size=n_samples)
    day_of_week = rng.integers(0, 7, size=n_samples)

    population_density = np.round(10 ** rng.uniform(1.5, 3.5, size=n_samples), 2)
    source_reliability = np.clip(rng.normal(0.8, 0.15, size=n_samples), 0.0, 1.0).round(3)

    hist_mean = np.array([0.65, 0.55, 0.5, 0.4, 0.5, 0.55, 0.55, 0.45])
    type_index = np.array([EVENT_TYPES.index(t) for t in types], dtype=int)
    hist_by_type = hist_mean[type_index]
    historical_frequency = np.clip(hist_by_type + rng.normal(0.0, 0.15, size=n_samples), 0.02, 0.98).round(3)

    temperature = np.clip(28.0 - np.abs(lat) * 0.25 + rng.normal(0.0, 5.0, size=n_samples), -30.0, 50.0).round(1)
    precipitation = np.clip(
        np.maximum(0.0, rng.normal(12.0, 18.0, size=n_samples))
        + 8.0 * np.sin((month - 6) / 12.0 * 2 * np.pi),
        0.0,
        120.0,
    ).round(1)
    wind_speed = np.clip(np.maximum(0.0, rng.normal(15.0, 18.0, size=n_samples)), 0.0, 180.0).round(1)

    # Amplitudes that let the weather signal correlate with event type.
    precip = precipitation.copy()
    wind = wind_speed.copy()
    temp = temperature.copy()
    precip[types == "flood"] += rng.uniform(25.0, 70.0, size=int((types == "flood").sum()))
    wind[types == "cyclone"] += rng.uniform(60.0, 120.0, size=int((types == "cyclone").sum()))
    temp[types == "drought"] += rng.uniform(3.0, 8.0, size=int((types == "drought").sum()))
    precip[types == "drought"] = np.clip(precip[types == "drought"] - 15.0, 0.0, 20.0)

    pop_factor = np.minimum(population_density / 1500.0, 1.0)
    hist_factor = np.minimum(historical_frequency / 1.0, 1.0)
    source_factor = source_reliability

    weather_factor = np.zeros(n_samples)
    weather_factor[types == "flood"] = np.minimum(precip[types == "flood"] / 90.0, 1.0)
    weather_factor[types == "cyclone"] = np.minimum(wind[types == "cyclone"] / 140.0, 1.0)
    weather_factor[types == "drought"] = np.clip((temp[types == "drought"] - 30.0) / 15.0, 0.0, 1.0)
    weather_factor[types == "earthquake"] = 0.5
    weather_factor[types == "epidemic"] = 0.5 * pop_factor[types == "epidemic"]
    weather_factor[types == "conflict"] = hist_factor[types == "conflict"]
    weather_factor[types == "food_crisis"] = hist_factor[types == "food_crisis"]
    weather_factor[types == "displacement"] = np.maximum(hist_factor[types == "displacement"], 0.3)

    base_severity = np.array([
        2.2, 2.0, 2.4, 2.1, 1.8, 2.3, 1.9, 1.7,
    ])[type_index]

    score = (
        base_severity
        + 1.6 * pop_factor
        + 1.2 * hist_factor
        + 1.2 * weather_factor
        + 0.4 * source_factor
        + rng.normal(0.0, 0.45, size=n_samples)
    )
    severity = np.clip(np.rint(score), 1, 5).astype(int)

    X = pd.DataFrame(
        {
            "event_type": types,
            "latitude": np.round(lat, 4),
            "longitude": np.round(lon, 4),
            "population_density_estimate": population_density,
            "historical_frequency_in_region": historical_frequency,
            "temperature": temp,
            "wind_speed": wind,
            "precipitation": precip,
            "month": month,
            "day_of_week": day_of_week,
            "source_reliability_score": source_reliability,
        }
    )
    return X, pd.Series(severity, name="severity")


def _validate_features(X: pd.DataFrame) -> pd.DataFrame:
    """Validate that ``X`` contains every feature column and return it re-ordered."""
    if not isinstance(X, pd.DataFrame):
        raise TypeError("X must be a pandas DataFrame")
    missing = [c for c in FEATURES if c not in X.columns]
    if missing:
        raise ValueError(f"Missing required feature columns: {missing}")
    return X[FEATURES].copy()


class CrisisClassifier:
    """XGBoost severity classifier wrapped in a scikit-learn ``Pipeline``.

    Attributes
    ----------
    pipeline : Pipeline or None
        The fitted preprocessing + classification pipeline.  ``None`` until
        :meth:`train` or :meth:`load_model` has run.
    cv_summary : list of dict or None
        Top ``RandomizedSearchCV`` results captured during training.
    """

    def __init__(
        self,
        model_path: str | Path = MODEL_PATH,
        n_jobs: int = -1,
        random_state: int = 42,
        seed: int | None = None,
    ) -> None:
        self.model_path = Path(model_path)
        self.n_jobs = n_jobs
        self.random_state = random_state
        # ``seed`` is accepted for backward compatibility with earlier configs.
        if seed is not None:
            self.random_state = seed
        self.pipeline: Pipeline | None = None
        self.cv_summary: list[dict[str, Any]] | None = None
        self._classifier: XGBClassifier | None = None
        # Maps the model's internal contiguous class index back to a real severity
        # level.  Populated during training (some levels may be absent in the data).
        self._index_to_severity: np.ndarray = np.asarray(SEVERITY_LEVELS, dtype=int)

    # ------------------------------------------------------------------ core
    def train(
        self,
        X: pd.DataFrame | None = None,
        y: pd.Series | np.ndarray | list[int] | None = None,
        n_iter: int = 20,
        cv_folds: int = 3,
        use_synthetic_data: bool = True,
        save: bool = True,
    ) -> dict[str, Any]:
        """Train the classifier.

        Splits ``X``/``y`` into stratified 70/15/15 train/validation/test sets,
        runs ``RandomizedSearchCV`` on the validation split to tune hyper-parameters,
        refits the best configuration on train + validation and finally scores it on
        the held-out test set.

        Parameters
        ----------
        X, y
            Feature frame and severity labels.  When both are ``None`` and
            ``use_synthetic_data`` is true a synthetic demo dataset is generated.
        n_iter
            Number of parameter settings sampled by ``RandomizedSearchCV``.
        cv_folds
            Number of cross-validation folds for ``RandomizedSearchCV``.
        use_synthetic_data
            If ``True`` and no data was provided, generate synthetic data.
        save
            Persist the fitted pipeline with :meth:`save_model` on completion.

        Returns
        -------
        dict
            Training summary containing split sizes, test-set metrics, the best
            hyper-parameters, the mean CV score and the top CV results.
        """
        if X is None and y is None:
            if not use_synthetic_data:
                raise ValueError("No training data provided and use_synthetic_data=False")
            logger.info("No training data provided - generating synthetic demo data")
            X, y = generate_synthetic_data(random_state=self.random_state)
        elif X is None or y is None:
            raise ValueError("Both X and y must be provided together, or neither")

        X = _validate_features(X)
        y = np.asarray(y, dtype=int).ravel()
        if len(X) != len(y):
            raise ValueError(f"X ({len(X)} rows) and y ({len(y)} rows) must have equal length")
        labels, counts = np.unique(y, return_counts=True)
        logger.info("Training on %d rows; label distribution: %s", len(y), dict(zip(labels, counts, strict=False)))
        if not np.all(np.isin(labels, SEVERITY_LEVELS)):
            raise ValueError(f"Labels must be within {SEVERITY_LEVELS}; got {labels.tolist()}")
        # XGBoost requires contiguous 0-indexed classes, so renumber the severity
        # levels actually present in the data; the public API stays 1..5.
        present = np.sort(np.unique(y))
        self._index_to_severity = present.astype(int)
        y = np.searchsorted(present, y)

        train_idx, temp_idx, val_idx, test_idx = self._stratified_split(X, y, cv_folds)

        X_train, X_val, X_test = X.iloc[train_idx], X.iloc[val_idx], X.iloc[test_idx]
        y_train, y_val, y_test = y[train_idx], y[val_idx], y[test_idx]

        pipeline = self._build_pipeline()

        search = RandomizedSearchCV(
            estimator=pipeline,
            param_distributions=_PARAM_DISTRIBUTIONS,
            n_iter=n_iter,
            cv=cv_folds,
            scoring="f1_macro",
            n_jobs=self.n_jobs,
            random_state=self.random_state,
            verbose=0,
            refit=True,
        )
        search.fit(X_train, y_train)

        logger.info("Best params: %s (CV f1_macro=%.4f)", search.best_params_, search.best_score_)

        # Refit best config on train + validation, then evaluate on the untouched test set.
        X_fit = pd.concat([X_train, X_val], axis=0)
        y_fit = np.concatenate([y_train, y_val]).ravel()
        best_pipeline = search.best_estimator_
        best_pipeline.fit(X_fit, y_fit)

        self.pipeline = best_pipeline
        self._classifier = best_pipeline.named_steps["clf"]
        self.cv_summary = self._summarize_cv(search)

        evaluation = self.evaluate(X_test, y_test)

        if save:
            self.save_model()

        return {
            "split_sizes": {
                "train": int(len(X_train)),
                "validation": int(len(X_val)),
                "test": int(len(X_test)),
            },
            "evaluation": evaluation,
            "best_params": search.best_params_,
            "best_cv_score": float(search.best_score_),
            "top_cv_results": self.cv_summary[:5],
            "random_state": self.random_state,
        }

    def predict(self, features: dict[str, Any] | pd.DataFrame) -> dict[str, Any] | pd.DataFrame:
        """Predict severity for one event (dict) or a batch of events (DataFrame).

        For a single dict the return value is::

            {
                "severity": int,
                "confidence": float,
                "probabilities": {1: float, 2: float, 3: float, 4: float, 5: float},
            }

        For a ``DataFrame`` the return value is a ``DataFrame`` with additional
        ``severity``, ``confidence`` and a ``prob_<level>`` column per severity class.
        """
        if self.pipeline is None:
            raise RuntimeError("Model has not been trained or loaded yet - call train() or load_model() first")

        if isinstance(features, dict):
            row = pd.DataFrame([features])
            X = _validate_features(row).copy()
            probs = self.pipeline.predict_proba(X)[0]
            predicted_idx = int(np.argmax(probs))
            probabilities = {int(sev): 0.0 for sev in SEVERITY_LEVELS}
            for i, sev in enumerate(self._index_to_severity):
                probabilities[int(sev)] = float(probs[i])
            return {
                "severity": int(self._index_to_severity[predicted_idx]),
                "confidence": float(np.max(probs)),
                "probabilities": probabilities,
            }

        if isinstance(features, pd.DataFrame):
            X = _validate_features(features).copy()
            probs = self.pipeline.predict_proba(X)
            out = features.copy()
            out["severity"] = self._index_to_severity[np.argmax(probs, axis=1)]
            out["confidence"] = np.max(probs, axis=1)
            for _i, cls in enumerate(SEVERITY_LEVELS):
                present = np.where(self._index_to_severity == cls)[0]
                out[f"prob_{cls}"] = probs[:, present[0]] if present.size else np.zeros(len(probs))
            return out

        raise TypeError("features must be a dict or a pandas DataFrame")

    def evaluate(
        self, X_test: pd.DataFrame, y_test: pd.Series | np.ndarray | list[int]
    ) -> dict[str, Any]:
        """Evaluate the fitted model on a test set.

        Returns ``f1_macro`` (float), ``accuracy`` (float), ``confusion_matrix``
        (nested list) and ``classification_report`` (str).
        """
        if self.pipeline is None:
            raise RuntimeError("Model has not been trained or loaded yet - call train() or load_model() first")
        X_test = _validate_features(X_test)
        y_true = np.asarray(y_test, dtype=int).ravel()
        y_pred = np.asarray(self.pipeline.predict(X_test))
        y_pred = self._index_to_severity[y_pred]
        y_true = self._align_labels(y_true)
        y_pred = self._align_labels(y_pred)

        return {
            "f1_macro": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
            "accuracy": float(np.mean(y_true == y_pred)),
            "confusion_matrix": confusion_matrix(
                y_true, y_pred, labels=SEVERITY_LEVELS
            ).tolist(),
            "classification_report": classification_report(
                y_true, y_pred, labels=SEVERITY_LEVELS, target_names=None, zero_division=0
            ),
        }

    def _align_labels(self, y: np.ndarray) -> np.ndarray:
        """Ensure labels are 1..5 regardless of how the user encoded them."""
        if np.all(np.isin(y, SEVERITY_LEVELS)):
            return y
        # Some callers may pass 0..4; map to 1..5.
        mapped = y + 1
        if np.all(np.isin(mapped, SEVERITY_LEVELS)):
            return mapped
        raise ValueError(
            f"y contains labels outside the supported set {SEVERITY_LEVELS}: {np.unique(y).tolist()}"
        )

    # ------------------------------------------------------------ persistence
    def save_model(self, path: str | Path | None = None) -> Path:
        """Serialize the pipeline (and its class mapping) with ``joblib``."""
        if self.pipeline is None:
            raise RuntimeError("Model has not been trained - nothing to save")
        dest = Path(path) if path else self.model_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {
                "pipeline": self.pipeline,
                "index_to_severity": self._index_to_severity,
            },
            dest,
        )
        logger.info("Saved classifier to %s", dest)
        return dest

    def load_model(self, path: str | Path | None = None) -> CrisisClassifier:
        """Load a previously saved pipeline with ``joblib``."""
        src = Path(path) if path else self.model_path
        if not src.exists():
            raise FileNotFoundError(f"Model file not found: {src}")
        payload = joblib.load(src)
        if isinstance(payload, dict) and "pipeline" in payload:
            self.pipeline = payload["pipeline"]
            self._index_to_severity = np.asarray(payload.get("index_to_severity", SEVERITY_LEVELS), dtype=int)
        else:
            self.pipeline = payload  # backwards-compatible with bare-pipeline dumps
        self._classifier = self.pipeline.named_steps.get("clf")
        logger.info("Loaded classifier from %s", src)
        return self

    # --------------------------------------------------------------- helpers
    def _build_pipeline(self) -> Pipeline:
        preprocessor = ColumnTransformer(
            transformers=[
                ("num", StandardScaler(), NUMERIC_FEATURES),
                (
                    "cat",
                    OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                    CATEGORICAL_FEATURES,
                ),
            ]
        )
        classifier = XGBClassifier(
            objective="multi:softprob",
            eval_metric="mlogloss",
            n_jobs=1,
            random_state=self.random_state,
        )
        return Pipeline(
            steps=[
                ("preprocess", preprocessor),
                ("clf", classifier),
            ]
        )

    def _stratified_split(
        self, X: pd.DataFrame, y: np.ndarray, cv_folds: int
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Returns (train_idx, temp_idx, val_idx, test_idx) for a 70/15/15 split."""
        for cls, count in zip(*np.unique(y, return_counts=True), strict=False):
            if count < max(5, cv_folds):
                logger.warning("Class %d has only %d samples - cross-validation may be unstable", cls, count)

        sss = StratifiedShuffleSplit(n_splits=1, test_size=0.30, random_state=self.random_state)
        train_idx, temp_idx = next(sss.split(X, y))

        temp_y = y[temp_idx]
        sss2 = StratifiedShuffleSplit(n_splits=1, test_size=0.5, random_state=self.random_state)
        val_pos, test_pos = next(sss2.split(X.iloc[temp_idx], temp_y))
        val_idx = temp_idx[val_pos]
        test_idx = temp_idx[test_pos]
        return train_idx, temp_idx, val_idx, test_idx

    @staticmethod
    def _summarize_cv(search: RandomizedSearchCV) -> list[dict[str, Any]]:
        """Extract then sort the CV results for a compact training summary."""
        results = search.cv_results_
        rows = []
        for params, mean_score, std_score in zip(
            results["params"], results["mean_test_score"], results["std_test_score"], strict=False
        ):
            rows.append(
                {
                    "params": {k.removeprefix("clf__"): v for k, v in params.items()},
                    "mean_f1_macro": float(mean_score),
                    "std_f1_macro": float(std_score),
                }
            )
        rows.sort(key=lambda r: r["mean_f1_macro"], reverse=True)
        return rows


__all__ = [
    "CrisisClassifier",
    "generate_synthetic_data",
    "SEVERITY_LEVELS",
    "SEVERITY_NAMES",
    "FEATURES",
    "EVENT_TYPES",
]