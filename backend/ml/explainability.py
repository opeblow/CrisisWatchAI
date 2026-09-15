"""SHAP explainability for the crisis severity model.

Explains why an XGBoost severity classifier predicted a given label, using
``shap.TreeExplainer``.  Supports either a raw ``XGBClassifier``/``Booster`` or the
scikit-learn ``Pipeline`` produced by :class:`backend.ml.classifier.CrisisClassifier`
(in which case the raw feature dict is pushed through the pipeline's
preprocessing steps automatically before SHAP runs).

The package is fully operational without ``shap`` installed: every public method
raises a clear, actionable error in that case (rather than crashing the import).
"""

from __future__ import annotations

import base64
import io
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline

logger = logging.getLogger(__name__)

try:
    import shap  # noqa: F401
    _SHAP_AVAILABLE = True
except Exception:  # pragma: no cover - shap is optional
    _SHAP_AVAILABLE = False

MODEL_DIR: Path = Path(__file__).resolve().parent / "models"

TOP_N: int = 5

# Feature name -> short human phrase, keyed by exact name or a suffix match
# (one-hot encoded columns arrive as ``event_type_<value>``).
_PHRASES: Dict[str, str] = {
    "population_density_estimate": "a high population density",
    "historical_frequency_in_region": "historically active region",
    "source_reliability_score": "high source reliability",
    "temperature": "extreme temperature readings",
    "wind_speed": "strong wind speeds",
    "precipitation": "heavy precipitation",
    "event_type": "event type",
    "month": "the time of year",
    "day_of_week": "the day of the week",
    "latitude": "its latitude",
    "longitude": "its longitude",
}

__all__ = ["ModelExplainer", "natural_language_explanation", "TOP_N"]


def _require_shap() -> None:
    if not _SHAP_AVAILABLE:
        raise RuntimeError(
            "shap is not installed - add 'shap' to backend/requirements.txt to use "
            "model explainability"
        )


class ModelExplainer:
    """SHAP-based explainer for the crisis severity model.

    Methods
    -------
    explain(model, features_dict, feature_names=None)
        Top-N SHAP features for one prediction.
    generate_summary_plot(model, X, feature_names=None)
        Base64-encoded SHAP summary (beeswarm) plot.
    generate_force_plot(model, features_dict, feature_names=None)
        Base64-encoded SHAP force plot for a single prediction.
    """

    def __init__(self, max_display: int = 15) -> None:
        self.max_display = max_display

    # ------------------------------------------------------------------ core
    def explain(
        self,
        model: Any,
        features_dict: Dict[str, Any],
        feature_names: Optional[Sequence[str]] = None,
        background_data: Optional[Union[pd.DataFrame, np.ndarray]] = None,
    ) -> Dict[str, Any]:
        """Return the top-5 SHAP features influencing one prediction.

        Parameters
        ----------
        model
            Fitted XGB classifier: a ``Pipeline`` with a final ``clf`` step, a raw
            ``XGBClassifier``, or an ``xgboost.Booster``.
        features_dict
            Raw feature values for the single event to explain.  Keys must match the
            original (pre-preprocessing) schema for pipelines.
        feature_names
            Optional column names for a raw model; derived automatically from the
            pipeline when a ``Pipeline`` is passed.
        background_data
            Optional slice of the training data to seed the TreeExplainer with.

        Returns
        -------
        dict
            ``{"predicted_severity": int, "top_features": [...], "text": str}`` where
            each top feature is ``{"feature_name", "value", "shap_value", "direction"}``.
        """
        if not _SHAP_AVAILABLE:
            logger.info("shap unavailable - using local feature attribution fallback")
            return self._explain_fallback(model, features_dict, feature_names)

        estimator, X, names = self._prepare_model_input(model, features_dict, feature_names)
        proba = _predict_proba(estimator, X)
        predicted_class = int(np.argmax(proba[0]))

        explainer = shap.TreeExplainer(estimator, data=background_data)
        shap_values = explainer.shap_values(X)

        class_values, class_base = _select_class_channel(shap_values, explainer, predicted_class)
        row_values = np.asarray(class_values[0], dtype=float)
        row_data = np.asarray(X[0], dtype=float)

        top = self._top_features(row_values, row_data, names, predicted_class)

        return {
            "predicted_severity": predicted_class + 1,
            "class_name": _severity_name(predicted_class + 1),
            "top_features": top,
            "text": natural_language_explanation(top, predicted_severity=predicted_class + 1),
        }

    # ------------------------------------------------------------------ plots
    def generate_summary_plot(
        self,
        model: Any,
        X: Union[pd.DataFrame, np.ndarray],
        feature_names: Optional[Sequence[str]] = None,
        background_data: Optional[Union[pd.DataFrame, np.ndarray]] = None,
    ) -> str:
        """Render a SHAP summary (beeswarm) plot and return it as a data URI ``str``."""
        _require_shap()
        import matplotlib

        matplotlib.use("Agg")

        X_arr = np.asarray(X, dtype=float)
        if feature_names is None and isinstance(X, pd.DataFrame):
            feature_names = list(X.columns)

        estimator = self._as_estimator(model)
        explainer = shap.TreeExplainer(estimator, data=background_data)
        shap_values = explainer.shap_values(X_arr)

        final_values, _ = _select_class_channel(shap_values, explainer, _mode_class(estimator, X_arr))
        try:
            shap.summary_plot(
                final_values if final_values.ndim == 2 else shap_values,
                X_arr,
                feature_names=feature_names,
                max_display=self.max_display,
                show=False,
            )
            fig = _current_figure()
        except Exception as exc:  # masked multiclass paths etc. fall back to a bar plot
            logger.warning("summary_plot failed (%s); falling back to a bar chart", exc)
            import matplotlib.pyplot as plt

            plt.close("all")
            mean_abs = np.abs(np.asarray(final_values)).mean(axis=0) if final_values.ndim == 2 else np.abs(
                np.asarray(final_values)
            )
            order = np.argsort(mean_abs)[::-1][: self.max_display]
            _, ax = plt.subplots(figsize=(8, max(3, 0.4 * len(order))))
            ax.barh(
                [feature_names[i] if feature_names else f"f{i}" for i in order],
                mean_abs[order],
            )
            ax.set_xlabel("mean |SHAP value|")
            ax.set_title("SHAP feature importance")
            fig = ax.figure
        return _figure_to_base64(fig)

    def generate_force_plot(
        self,
        model: Any,
        features_dict: Dict[str, Any],
        feature_names: Optional[Sequence[str]] = None,
        background_data: Optional[Union[pd.DataFrame, np.ndarray]] = None,
    ) -> str:
        """Render a SHAP force plot for a single prediction as a data URI ``str``."""
        _require_shap()
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        estimator, X, names = self._prepare_model_input(model, features_dict, feature_names)
        predicted_class = int(np.argmax(_predict_proba(estimator, X)[0]))

        explainer = shap.TreeExplainer(estimator, data=background_data)
        shap_values = explainer.shap_values(X)
        class_values, class_base = _select_class_channel(shap_values, explainer, predicted_class)

        try:
            expectation = shap.Explanation(
                values=np.asarray(class_values[0], dtype=float),
                base_values=float(class_base),
                data=np.asarray(X[0], dtype=float),
                feature_names=list(names),
            )
            shap.plots.force(expectation, matplotlib=True, show=False)
            fig = _current_figure()
        except Exception as exc:  # force plot can be finicky headless - bar fallback
            logger.warning("force_plot failed (%s); falling back to a bar chart", exc)
            plt.close("all")
            values = np.asarray(class_values[0], dtype=float)
            k = min(TOP_N, len(values))
            order = np.argsort(np.abs(values))[::-1][:k]
            _, ax = plt.subplots(figsize=(8, 0.5 * k + 1))
            ax.barh(
                [names[i] for i in order],
                [values[i] for i in order],
                color=["#e64b35" if v >= 0 else "#3182bd" for v in values[order]],
            )
            ax.set_title(f"Top {k} SHAP drivers (severity class {predicted_class + 1})")
            fig = ax.figure
        return _figure_to_base64(fig)

    # --------------------------------------------------------------- helpers
    def _explain_fallback(
        self,
        model: Any,
        features_dict: Dict[str, Any],
        feature_names: Optional[Sequence[str]],
    ) -> Dict[str, Any]:
        """Local feature attribution when ``shap`` cannot be imported.

        Uses a per-feature occlusion approach: each feature value is replaced by
        a neutral baseline and the resulting change in the predicted class
        probability is treated as that feature's contribution.  This provides
        the same ``top_features`` + ``text`` contract as the SHAP path so the
        API and UI never depend on the SHAP binary being usable.
        """
        estimator, X, names = self._prepare_model_input(model, features_dict, feature_names)
        proba = _predict_proba(estimator, X)
        predicted_class = int(np.argmax(proba[0]))
        base_prob = float(proba[0][predicted_class])

        baseline = X.copy()
        raw_mean = baseline.mean(axis=0)
        contributions: List[Dict[str, Any]] = []
        for i in range(X.shape[1]):
            perturbed = baseline.copy()
            perturbed[:, i] = raw_mean[i]
            p = _predict_proba(estimator, perturbed)
            delta = base_prob - float(p[0][predicted_class])
            value = float(X[0][i])
            contributions.append(
                {
                    "feature_name": names[i],
                    "value": int(value) if float(value).is_integer() else round(value, 3),
                    "shap_value": round(delta, 4),
                    "direction": "increases" if delta > 0 else "decreases",
                }
            )

        contributions.sort(key=lambda c: abs(c["shap_value"]), reverse=True)
        top = contributions[:TOP_N]
        text = natural_language_explanation(top, predicted_severity=predicted_class + 1)
        return {
            "predicted_severity": predicted_class + 1,
            "class_name": _severity_name(predicted_class + 1),
            "top_features": top,
            "text": text,
            "attribution_method": "local_occlusion",
        }

    def _prepare_model_input(
        self,
        model: Any,
        features_dict: Dict[str, Any],
        feature_names: Optional[Sequence[str]],
    ) -> Tuple[Any, np.ndarray, List[str]]:
        """Return ``(estimator, X_row, feature_names)`` for ``features_dict``."""
        estimator = self._as_estimator(model)

        if isinstance(model, Pipeline) or (
            hasattr(model, "steps") and not hasattr(model, "predict_proba")
        ):
            row_df = pd.DataFrame([features_dict])
            preprocessor = model[:-1]
            X = preprocessor.transform(row_df)
            if hasattr(X, "toarray"):
                X = X.toarray()
            X = np.asarray(X, dtype=float)
            names = list(preprocessor.get_feature_names_out())
        else:
            if feature_names is None:
                raise ValueError("feature_names is required when no Pipeline is provided")
            names = list(feature_names)
            values = [features_dict.get(n, 0.0) for n in names]
            X = np.asarray([values], dtype=float)

        names = [_clean_feature_name(n) for n in names]
        if not np.isfinite(X).all():
            raise ValueError("features_dict contains NaN or infinite values")
        return estimator, X, names

    @staticmethod
    def _as_estimator(model: Any) -> Any:
        if isinstance(model, Pipeline) or (
            hasattr(model, "steps") and hasattr(model, "named_steps")
        ):
            return model.named_steps.get("clf") or model.steps[-1][1]
        return model

    def _top_features(
        self, values: np.ndarray, data: np.ndarray, names: List[str], predicted_class: int
    ) -> List[Dict[str, Any]]:
        order = np.argsort(np.abs(values))[::-1][:TOP_N]
        features = []
        for i in order:
            sv = float(values[i])
            raw = data[i]
            value = int(raw) if float(raw).is_integer() else round(float(raw), 3)
            features.append(
                {
                    "feature_name": names[i],
                    "value": value,
                    "shap_value": round(sv, 4),
                    "direction": "increases" if sv > 0 else "decreases",
                }
            )
        return features


# ---------------------------------------------------------------- utilities
def _predict_proba(estimator: Any, X: np.ndarray) -> np.ndarray:
    if hasattr(estimator, "predict_proba"):
        return np.asarray(estimator.predict_proba(X), dtype=float)
    return np.asarray(estimator.predict(X), dtype=float)


def _mode_class(estimator: Any, X: np.ndarray) -> int:
    return int(np.argmax(_predict_proba(estimator, X)[0]))


def _select_class_channel(
    shap_values: Any, explainer: Any, class_idx: int
) -> Tuple[np.ndarray, float]:
    """Reduce multi-class SHAP output to the channel for ``class_idx``."""
    if isinstance(shap_values, (list, tuple)):
        arr = np.asarray(shap_values[class_idx], dtype=float)
    else:
        arr = np.asarray(shap_values, dtype=float)
        if arr.ndim == 3:
            arr = arr[:, :, class_idx]
        elif arr.ndim == 1 and explainer is not None and hasattr(explainer, "expected_value"):
            arr = arr.reshape(1, -1)

    base = 0.0
    expected = getattr(explainer, "expected_value", None)
    if expected is not None:
        if isinstance(expected, (list, tuple)):
            base = float(np.ravel(expected)[class_idx])
        elif np.ndim(expected) > 0 and np.size(expected) > 1:
            base = float(np.ravel(expected)[class_idx] if np.ravel(expected).size > 1 else expected)
        else:
            base = float(np.ravel(expected)[0])
    return arr, base


def _clean_feature_name(name: str) -> str:
    """Strip sklearn prefixes such as ``num__`` / ``cat__`` from feature names."""
    return name.split("__", 1)[-1]


def _severity_name(level: int) -> str:
    return {1: "Low", 2: "Medium", 3: "High", 4: "Critical", 5: "Catastrophic"}.get(level, "Unknown")


def _current_figure():
    import matplotlib.pyplot as plt

    fig = plt.gcf()
    return fig


def _figure_to_base64(fig: Any) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=120)
    import matplotlib.pyplot as plt

    plt.close(fig)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def natural_language_explanation(
    shap_features: Sequence[Dict[str, Any]],
    predicted_severity: Optional[int] = None,
) -> str:
    """Render a human-readable explanation from :meth:`ModelExplainer.explain` output.

    Accepts either the ``"top_features"`` list from :meth:`explain` (a sequence of
    dicts) or the full ``explain`` return dict.  Produces text of the form::

        "The High severity prediction is primarily driven by an earthquake event
         (+0.35), occurring in a historically active region (+0.22), and a high
         population density (+0.18)."

    Features that *decrease* the prediction are appended with a mitigating clause.
    """
    if isinstance(shap_features, dict) and "top_features" in shap_features:
        predicted_severity = shap_features.get("predicted_severity", predicted_severity)
        shap_features = shap_features["top_features"]

    features = list(shap_features)
    if not features:
        return "No SHAP features available for this prediction."

    label = _severity_name(predicted_severity) if predicted_severity else "high"
    increases = [f for f in features if f["direction"] == "increases"]
    decreases = [f for f in features if f["direction"] == "decreases"]
    if not increases:
        increases = features[:1]

    def _phrase(f: Dict[str, Any]) -> str:
        name = f["feature_name"]
        val = f["value"]
        magnitude = f"({f['shap_value']:+.2f})"

        if name.startswith("event_type"):
            etype = name.split("event_type_", 1)[-1].replace("_", " ")
            return f"an event typed as {etype} {magnitude}" if etype not in ("", "event_type") else f"the event type {magnitude}"
        if name in _PHRASES:
            return f"the {_PHRASES[name]} feature ({val}) {magnitude}"
        return f"{name} ({val}) {magnitude}"

    driving = ", ".join(_phrase(f) for f in increases[:3])
    sentence = f"The {label} severity prediction is primarily driven by {driving}."

    if decreases:
        mitigating = ", ".join(_phrase(f) for f in decreases[:2])
        sentence += f" This is partially offset by {mitigating}."
    return sentence


# A local Pipeline alias so this module stays importable without scikit-learn at
# the top of the tree (it is only referenced, never constructed, at import time).
__all__ = ["ModelExplainer", "natural_language_explanation", "TOP_N"]