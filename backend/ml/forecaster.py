"""Time-series crisis-event forecaster built on Prophet.

Forecasts the future volume of crisis events from an aggregated time series of
daily/weekly counts.  Each row of the training frame must contain at least
``ds`` (datetime) and ``y`` (numeric count).  Any additional numeric columns are
registered as Prophet regressors and must be supplied for future periods when
making predictions.

Typical usage::

    from backend.ml.forecaster import CrisisForecaster, aggregate_crises

    series = aggregate_crises(events_df, group_by="type", freq="W")
    fc = CrisisForecaster()
    fc.train(series[series.group == "flood"][["ds", "y"]])
    forecast = fc.predict(periods=12, freq="W")
    cv = fc.cross_validate(n_splits=3)
"""

from __future__ import annotations

import logging
import pickle
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

MODEL_DIR: Path = Path(__file__).resolve().parent / "models"
MODEL_PATH: Path = MODEL_DIR / "crisis_forecaster.pkl"


def aggregate_crises(
    events: pd.DataFrame,
    group_by: str | None = "type",
    freq: str = "W",
    date_column: str = "date",
    count_column: str | None = None,
) -> pd.DataFrame:
    """Roll crisis events up into a (ds, group, y) long-form time series.

    Parameters
    ----------
    events
        DataFrame containing a date-like column and, optionally, a grouping column
        (defaults to the column named ``type``).
    group_by
        Column name to group events by.  Use ``"total"`` or ``None`` to collapse
        all events into a single series.
    freq
        Pandas resample frequency, e.g. ``"D"``, ``"W"``, ``"MS"``.
    date_column
        Name of the date column in ``events`` (also accepts ``"ds"`` automatically).
    count_column
        Optional column to sum per bucket.  When ``None`` each row counts as one event.

    Returns
    -------
    DataFrame
        Long-form with columns ``ds`` (datetime), ``group`` (str) and ``y`` (int).
    """
    if not isinstance(events, pd.DataFrame) or events.empty:
        raise ValueError("events must be a non-empty DataFrame")

    df = events.copy()
    ds_col = date_column if date_column in df.columns else ("ds" if "ds" in df.columns else None)
    if ds_col is None:
        raise ValueError(
            f"events must contain a '{date_column}' (or 'ds') column; found {list(df.columns)}"
        )
    df[ds_col] = pd.to_datetime(df[ds_col], errors="raise")
    if ds_col != "ds":
        df = df.rename(columns={ds_col: "ds"})

    value = df[count_column] if count_column else pd.Series(1, index=df.index)

    if group_by is None or group_by == "total":
        if count_column:
            out = value.groupby(pd.Grouper(key="ds", freq=freq)).sum().rename("y").reset_index()
        else:
            out = df.groupby(pd.Grouper(key="ds", freq=freq)).size().rename("y").reset_index()
        out.columns = ["ds", "y"]
        out["group"] = "total"
        return out[["ds", "group", "y"]]

    if group_by not in df.columns:
        raise ValueError(
            f"group_by column '{group_by}' not found in events; available: {list(df.columns)}"
        )
    if count_column:
        grouper = [pd.Grouper(key="ds", freq=freq), df[group_by]]
        out = value.groupby(grouper).sum().rename("y").reset_index()
    else:
        out = df.groupby([pd.Grouper(key="ds", freq=freq), group_by]).size().rename("y").reset_index()
    out.columns = ["ds", group_by, "y"]
    out["group"] = out[group_by].astype(str)
    return out[["ds", "group", "y"]]


class CrisisForecaster:
    """Prophet wrapper for forecasting crisis-event counts over time.

    Attributes
    ----------
    model
        Fitted ``prophet.Prophet`` instance or ``None`` until :meth:`train`.
    regressors : list of str
        Extra numeric columns registered via ``add_regressor`` (empty for a
        plain univariate series).
    freq : str
        Inferred observation frequency used for future frames.
    """

    def __init__(self, model_path: str | Path = MODEL_PATH, seed: int = 42) -> None:
        self.model_path = Path(model_path)
        self.seed = seed
        self.model: Any = None
        self.regressors: list[str] = []
        self.freq: str = "D"
        self._training_df: pd.DataFrame | None = None

    # ------------------------------------------------------------------ train
    def train(self, df: pd.DataFrame) -> dict[str, Any]:
        """Fit a Prophet model on a ``(ds, y)`` frame, registering extra regressors.

        Parameters
        ----------
        df
            DataFrame with ``ds`` (datetime) and ``y`` (numeric).  Additional numeric
            columns are treated as regressors for the whole forecast horizon.
        """
        if not isinstance(df, pd.DataFrame) or df.empty:
            raise ValueError("df must be a non-empty DataFrame")
        if not {"ds", "y"}.issubset(df.columns):
            raise ValueError("df must contain 'ds' and 'y' columns")

        train = df.copy()
        train["ds"] = pd.to_datetime(train["ds"], errors="raise")
        train = train.dropna(subset=["y"]).sort_values("ds")
        if train.empty:
            raise ValueError("No valid (ds, y) rows after cleaning")

        # Infer the dominant sampling frequency.
        inferred = pd.infer_freq(train["ds"].drop_duplicates())
        self.freq = inferred if inferred else self._guess_freq(train["ds"])
        logger.info("Inferred sampling frequency: %s", self.freq)

        self.regressors = [
            c for c in train.columns if c not in ("ds", "y") and pd.api.types.is_numeric_dtype(train[c])
        ]
        try:
            self._train_prophet(train)
            self.backend = "prophet"
        except ImportError as exc:
            logger.warning("prophet not installed (%s); using seasonal-naive fallback", exc)
            self._train_naive(train)
            self.backend = "seasonal_naive"

        return {
            "rows": int(len(train)),
            "regressors": self.regressors,
            "freq": self.freq,
            "backend": self.backend,
        }

    # ---------------------------------------------------------------- backends
    def _train_prophet(self, train: pd.DataFrame) -> None:
        from prophet import Prophet  # heavy import kept lazy

        model = Prophet(
            yearly_seasonality=True,
            weekly_seasonality=True,
            daily_seasonality=False,
            seasonality_mode="additive",
        )
        for name in self.regressors:
            model.add_regressor(name)
        model.fit(train[["ds", "y"] + self.regressors])
        self.model = model
        self._training_df = train[["ds", "y"] + self.regressors]

    def _train_naive(self, train: pd.DataFrame) -> None:
        """Fit a lightweight seasonal-naive baseline model with numpy.

        Used when Prophet is not installed so the forecasting endpoint still
        returns meaningful point + interval forecasts.  Weekly seasonality is
        captured by a per-day-of-week mean; a linear trend is fit on the
        remainder; forecast noise is scaled by the training residual std.
        """
        target = train.set_index("ds")["y"]
        first = train["ds"].min()
        last = train["ds"].max()
        td = pd.Timedelta(1, unit="D") if self.freq.startswith("D") else pd.Timedelta(7, unit="D")

        x = (train["ds"] - first).dt.days.astype(float).values
        y = target.values.astype(float)
        trend_coef = np.polyfit(x, y, 1)
        trend_values = np.polyval(trend_coef, x)

        detrended = y - trend_values
        dow_series = pd.Series(detrended, index=train["ds"].dt.dayofweek)
        dow_means = dow_series.groupby(dow_series.index).mean().reindex(range(7), fill_value=0.0)

        resid = detrended - np.array([dow_means[d.dayofweek] for d in train["ds"]])

        self._model_naive = {
            "first": first,
            "last": last,
            "step": td,
            "dow_means": dow_means.values,
            "trend_coef": trend_coef,
            "resid_std": float(np.std(resid)) if len(resid) > 1 else 1.0,
            "mean": float(y.mean()) if len(y) else 0.0,
        }
        self.model = {"kind": "seasonal_naive"}
        self._training_df = train[["ds", "y"]]

    def _predict_naive(self, periods: int, freq: str) -> pd.DataFrame:
        p = self._model_naive
        start_date = p["last"] + p["step"]
        horizon = pd.date_range(start=start_date, periods=periods, freq=freq)
        days = (pd.Series(horizon) - p["first"]).dt.days.astype(float).values
        seasonal = np.array([p["dow_means"][d.dayofweek] for d in horizon])
        trend = np.polyval(p["trend_coef"], days)
        yhat = trend + seasonal
        yhat = np.maximum(yhat, 0.0)
        sigma = p["resid_std"] * np.sqrt(1 + np.arange(periods) / max(periods, 1))
        return pd.DataFrame({
            "ds": horizon,
            "yhat": yhat,
            "yhat_lower": np.maximum(0.0, yhat - 1.96 * sigma),
            "yhat_upper": yhat + 1.96 * sigma,
        })

    # ----------------------------------------------------------------- predict
    def predict(
        self,
        periods: int = 30,
        freq: str = "D",
        future_regressors: pd.DataFrame | dict[str, list[Any]] | None = None,
        include_history: bool = True,
    ) -> pd.DataFrame:
        """Forecast ``periods`` future observations at frequency ``freq``.

        If the model was trained with regressors, ``future_regressors`` must supply
        their future values (a DataFrame with a ``ds`` column, or a dict mapping
        regressor name to a list of length ``periods``).

        Returns a DataFrame with columns ``ds``, ``yhat``, ``yhat_lower``,
        ``yhat_upper``.
        """
        if self.model is None:
            raise RuntimeError("Model has not been trained - call train() first")
        if periods < 1:
            raise ValueError("periods must be >= 1")

        if getattr(self, "backend", "prophet") == "seasonal_naive":
            return self._predict_naive(periods, freq)

        future = self.model.make_future_dataframe(
            periods=periods, freq=freq, include_history=include_history
        )

        if self.regressors:
            fr = self._prepare_future_regressors(future, future_regressors, periods)
            future = future.merge(fr, on="ds", how="left")

        forecast = self.model.predict(future)
        return forecast[["ds", "yhat", "yhat_lower", "yhat_upper"]]

    # --------------------------------------------------------- cross-validation
    def cross_validate(self, n_splits: int = 3, freq: str | None = None) -> dict[str, Any]:
        """Back-test the fitted series with ``TimeSeriesSplit``.

        Walks forward through the training history; for each fold a fresh Prophet
        model is fit on the train portion and evaluated on the following horizon.
        Regressors are ignored during cross-validation (univariate folds).

        Returns summary metrics ``mape`` (%), ``rmse`` (absolute units) plus a per-fold
        detail list.  Raises if the series is too short for the requested splits.
        """
        if self._training_df is None:
            raise RuntimeError("Model has not been trained - call train() first")

        from sklearn.model_selection import TimeSeriesSplit

        frame = self._training_df[["ds", "y"]].sort_values("ds").reset_index(drop=True)
        n = len(frame)
        if n < n_splits + 2:
            raise ValueError(f"Need at least {n_splits + 2} observations for {n_splits} splits; got {n}")

        if getattr(self, "backend", "prophet") == "seasonal_naive":
            return self._cross_validate_naive(frame, n_splits, freq)

        from prophet import Prophet

        freq = freq or self.freq or "D"
        tscv = TimeSeriesSplit(n_splits=n_splits)
        folds: list[dict[str, Any]] = []
        all_mape, all_rmse = [], []

        for fold, (train_idx, test_idx) in enumerate(tscv.split(frame), start=1):
            train_fold = frame.iloc[train_idx]
            test_fold = frame.iloc[test_idx]
            horizon = len(test_fold)

            model = Prophet(
                yearly_seasonality=True,
                weekly_seasonality=True,
                daily_seasonality=False,
            )
            model.fit(train_fold)
            future = model.make_future_dataframe(periods=horizon, freq=freq)
            fc = model.predict(future).tail(horizon)

            y_true = test_fold["y"].to_numpy(dtype=float)
            y_pred = fc["yhat"].to_numpy(dtype=float)
            denom = np.where(y_true == 0, np.nan, np.abs(y_true))
            mape = float(np.nanmean(np.abs(y_true - y_pred) / denom) * 100) if y_true.size else 0.0
            rmse = float(np.sqrt(np.mean((y_true - y_pred) ** 2)))

            all_mape.append(mape)
            all_rmse.append(rmse)
            folds.append(
                {
                    "fold": fold,
                    "train_rows": int(len(train_idx)),
                    "test_rows": horizon,
                    "mape": round(mape, 4),
                    "rmse": round(rmse, 4),
                }
            )

        return {
            "mape": round(float(np.nanmean(all_mape)), 4),
            "rmse": round(float(np.mean(all_rmse)), 4),
            "n_splits": n_splits,
            "freq": freq,
            "folds": folds,
        }

    def _cross_validate_naive(
        self, frame: pd.DataFrame, n_splits: int, freq: str | None
    ) -> dict[str, Any]:
        """Walk-forward validation for the seasonal-naive fallback model."""
        from sklearn.model_selection import TimeSeriesSplit

        freq = freq or self.freq or "D"
        tscv = TimeSeriesSplit(n_splits=n_splits)
        folds: list[dict[str, Any]] = []
        all_mape, all_rmse = [], []

        for fold, (train_idx, test_idx) in enumerate(tscv.split(frame), start=1):
            train_fold = frame.iloc[train_idx].copy()
            test_fold = frame.iloc[test_idx]
            horizon = len(test_fold)

            self._train_naive(train_fold)
            fc = self._predict_naive(horizon, freq)
            y_true = test_fold["y"].to_numpy(dtype=float)
            y_pred = fc["yhat"].to_numpy(dtype=float)[: horizon]

            denom = np.where(y_true == 0, np.nan, np.abs(y_true))
            mape = float(np.nanmean(np.abs(y_true - y_pred) / denom) * 100) if y_true.size else 0.0
            rmse = float(np.sqrt(np.mean((y_true - y_pred) ** 2)))
            all_mape.append(mape)
            all_rmse.append(rmse)
            folds.append(
                {
                    "fold": fold,
                    "train_rows": int(len(train_idx)),
                    "test_rows": horizon,
                    "mape": round(mape, 4),
                    "rmse": round(rmse, 4),
                }
            )

        return {
            "mape": round(float(np.nanmean(all_mape)), 4),
            "rmse": round(float(np.mean(all_rmse)), 4),
            "n_splits": n_splits,
            "freq": freq,
            "folds": folds,
            "backend": "seasonal_naive",
        }

    def _train_naive_for_cv(self, df: pd.DataFrame) -> None:
        self.backend = "seasonal_naive"
        self._train_naive(df)

    # ------------------------------------------------------------ persistence
    def save_model(self, path: str | Path | None = None) -> Path:
        """Serialize the fitted Prophet model (and config) with ``pickle``."""
        if self.model is None:
            raise RuntimeError("Model has not been trained - nothing to save")
        dest = Path(path) if path else self.model_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as fh:
            pickle.dump(
                {
                    "model": self.model,
                    "regressors": self.regressors,
                    "freq": self.freq,
                    "seed": self.seed,
                    "backend": getattr(self, "backend", "prophet"),
                    "model_naive": getattr(self, "_model_naive", None),
                },
                fh,
            )
        logger.info("Saved forecaster to %s", dest)
        return dest

    def load_model(self, path: str | Path | None = None) -> CrisisForecaster:
        """Restore a forecaster previously saved with :meth:`save_model`."""
        src = Path(path) if path else self.model_path
        if not src.exists():
            raise FileNotFoundError(f"Model file not found: {src}")
        with open(src, "rb") as fh:
            payload = pickle.load(fh)
        self.model = payload["model"]
        self.regressors = list(payload.get("regressors", []))
        self.freq = payload.get("freq", "D")
        self.seed = int(payload.get("seed", 42))
        self.backend = payload.get("backend", "prophet")
        self._model_naive = payload.get("model_naive", None)
        logger.info("Loaded forecaster from %s", src)
        return self

    # --------------------------------------------------------------- helpers
    def _prepare_future_regressors(
        self,
        future: pd.DataFrame,
        future_regressors: pd.DataFrame | dict[str, list[Any]] | None,
        periods: int,
    ) -> pd.DataFrame:
        """Validate and align user-supplied future regressor values to ``future.ds``."""
        if future_regressors is None:
            raise ValueError(
                f"This model uses regressors {self.regressors}; pass future_regressors "
                "with their projected values for the next "
                f"{periods} periods."
            )

        if isinstance(future_regressors, dict):
            fr = dict(future_regressors)
            fr.setdefault("ds", list(pd.to_datetime(future["ds"]))[-periods:])
            fr = pd.DataFrame(fr)
        else:
            fr = future_regressors.copy()

        missing = [r for r in self.regressors if r not in fr.columns]
        if missing:
            raise ValueError(f"future_regressors missing columns: {missing}")

        fr["ds"] = pd.to_datetime(fr["ds"], errors="raise")
        merged = future[["ds"]].merge(fr, on="ds", how="left")
        bad = merged[self.regressors].isna().any(axis=1).sum()
        if bad:
            raise ValueError(
                f"{bad} future timestamp(s) lack regressor values; supply a value for "
                "every future 'ds'."
            )
        return fr

    @staticmethod
    def _guess_freq(ds: pd.Series) -> str:
        deltas = ds.diff().dropna()
        if deltas.empty:
            return "D"
        median = deltas.median()
        if median >= pd.Timedelta(days=350):
            return "Y"
        if median >= pd.Timedelta(days=30):
            return "MS"
        if median >= pd.Timedelta(days=6):
            return "W"
        if median >= pd.Timedelta(hours=22):
            return "D"
        if median >= pd.Timedelta(hours=1):
            return "h"
        return "D"


__all__ = ["CrisisForecaster", "aggregate_crises"]