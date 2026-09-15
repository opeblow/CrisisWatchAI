"""Spatial crisis clustering using HDBSCAN.

Groups crisis events into geo-spatial hotspots with a risk score formed from the
cluster's event density, its average severity and the maximum possible severity::

    risk_score = cluster_density * avg_severity / max_possible

Density is expressed relative to the densest hotspot found in the data so the
score always lands in ``(0, 1]`` when all hotspots share the same severity.

Typical usage::

    from backend.ml.clustering import CrisisClustering

    cc = CrisisClustering()
    labels = cc.fit_predict(events_df)
    hotspots = cc.get_hotspots()
    enriched = cc.add_cluster_labels(events_df)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

try:
    import hdbscan  # noqa: F401  (validated lazily in fit_predict)
    _HDBSCAN_AVAILABLE = True
except Exception:  # pragma: no cover
    _HDBSCAN_AVAILABLE = False

LAT_COLS = ["latitude", "lat"]
LON_COLS = ["longitude", "lon"]
SEV_COLS = ["severity", "severity_score", "risk_level"]

MODEL_DIR: Path = Path(__file__).resolve().parent / "models"
HOTSPOTS_PATH: Path = MODEL_DIR / "crisis_hotspots.pkl"

EARTH_RADIUS_KM: float = 6371.0
MAX_SEVERITY: float = 5.0

__all__ = ["CrisisClustering", "HOTSPOTS_PATH"]


def _resolve_column(df: pd.DataFrame, candidates: List[str], purpose: str) -> str:
    for col in candidates:
        if col in df.columns:
            return col
    raise ValueError(
        f"{purpose} column not found in events DataFrame; expected one of {candidates}"
    )


class CrisisClustering:
    """HDBSCAN-based spatial clustering of crisis events.

    Attributes
    ----------
    labels_ : np.ndarray or None
        Cluster label per fitted row (-1 == noise).  ``None`` until :meth:`fit_predict`.
    hotspots_ : list of dict or None
        Computed hotspot summaries; populated by :meth:`get_hotspots`.
    """

    def __init__(
        self,
        min_cluster_size: int = 5,
        min_samples: int = 3,
        cluster_selection_epsilon: Optional[float] = None,
        **hdbscan_kwargs: Any,
    ) -> None:
        if min_cluster_size < 2:
            raise ValueError("min_cluster_size must be >= 2")

        self.min_cluster_size = min_cluster_size if _HDBSCAN_AVAILABLE else 3
        self.min_samples = min_samples
        self.cluster_selection_epsilon = cluster_selection_epsilon
        self.hdbscan_kwargs = hdbscan_kwargs
        self.labels_: Optional[np.ndarray] = None
        self.hotspots_: Optional[List[Dict[str, Any]]] = None
        self._fitted_df: Optional[pd.DataFrame] = None
        self._lat_col: Optional[str] = None
        self._lon_col: Optional[str] = None
        self._sev_col: Optional[str] = None

    # ------------------------------------------------------------------ fit
    def fit_predict(self, events_df: pd.DataFrame) -> np.ndarray:
        """Fit HDBSCAN on ``(latitude, longitude)`` and return per-event labels.

        Lat/lon pairs are converted to radians and clustered with the haversine
        metric so distances are true great-circle distances.  ``-1`` marks noise.
        """
        if not isinstance(events_df, pd.DataFrame) or events_df.empty:
            raise ValueError("events_df must be a non-empty DataFrame")

        self._lat_col = _resolve_column(events_df, LAT_COLS, "latitude")
        self._lon_col = _resolve_column(events_df, LON_COLS, "longitude")
        self._sev_col = next((c for c in SEV_COLS if c in events_df.columns), None)

        coords = events_df[[self._lat_col, self._lon_col]].to_numpy(dtype=float)
        if not np.isfinite(coords).all():
            raise ValueError("latitude/longitude columns contain NaN or infinite values")

        radians = np.radians(coords)
        if _HDBSCAN_AVAILABLE:
            model = hdbscan.HDBSCAN(
                min_cluster_size=self.min_cluster_size,
                min_samples=self.min_samples,
                cluster_selection_epsilon=self.cluster_selection_epsilon,
                metric="haversine",
                algorithm="generic",  # required for haversine distances
                **self.hdbscan_kwargs,
            )
            self.labels_ = model.fit_predict(radians)
        else:
            self.labels_ = self._dbscan_fallback(coords)
        self._fitted_df = events_df.reset_index(drop=True).copy()
        self.hotspots_ = None  # invalidate stale summaries
        logger.info(
            "Clustered %d events into %d hotspots (%d noise points)",
            len(events_df), int((self.labels_ >= 0).sum()), int((self.labels_ == -1).sum()),
        )
        return self.labels_

    # ---------------------------------------------------------------------------
    def _dbscan_fallback(self, coords: np.ndarray) -> np.ndarray:
        """DBSCAN stand-in when the hdbscan package is not installed.

        Uses a simple fixed-radius grouping on (lat, lon): points closer than
        ``radius_km`` are merged into the same cluster greedily, otherwise
        marked as noise (-1).  Mirrors HDBSCAN's contract well enough for the
        hotspot endpoint.
        """
        from sklearn.cluster import DBSCAN

        radius_km = self.cluster_selection_epsilon * EARTH_RADIUS_KM if self.cluster_selection_epsilon else 40.0
        eps = np.radians(radius_km / EARTH_RADIUS_KM)
        model = DBSCAN(eps=eps, min_samples=self.min_samples, metric="haversine")
        labels = model.fit_predict(np.radians(coords))
        logger.info("hdbscan unavailable - used DBSCAN fallback (eps=%.3f km)", radius_km)
        return labels

    # --------------------------------------------------------------- hotspots
    def get_hotspots(self, default_severity: float = 1.0) -> List[Dict[str, Any]]:
        """Compute hotspot summaries, sorted by descending ``risk_score``.

        Each hotspot is ``{"cluster_id", "center_lat", "center_lon", "event_count",
        "avg_severity", "risk_score"}``.  ``risk_score`` combines each cluster's
        relative density with its mean severity::

            risk_score = (density / max_density) * avg_severity / max_possible
        """
        if self.labels_ is None or self._fitted_df is None:
            raise RuntimeError("No fitted clusters - call fit_predict() first")

        df = self._fitted_df.copy()
        df["_cluster"] = self.labels_

        clusters = [
            g for name, g in df.groupby("_cluster") if int(name) >= 0  # drop noise (-1)
        ]
        if not clusters:
            return []

        lat = df[self._lat_col].to_numpy(float)
        lon = df[self._lon_col].to_numpy(float)
        if self._sev_col:
            sev = df[self._sev_col].to_numpy(float)
        else:
            sev = np.full(len(df), float(default_severity))

        hotspot_rows: List[Dict[str, Any]] = []
        for g in clusters:
            idx = g.index.to_numpy()
            cid = int(g.name)
            center_lat = float(lat[idx].mean())
            center_lon = float(lon[idx].mean())
            count = int(len(idx))
            avg_sev = float(sev[idx].mean())
            density = count / max(self._approx_area_km2(lat[idx], lon[idx]), 1.0)
            hotspot_rows.append(
                {
                    "cluster_id": cid,
                    "center_lat": round(center_lat, 5),
                    "center_lon": round(center_lon, 5),
                    "event_count": count,
                    "avg_severity": round(avg_sev, 3),
                    "_density": density,
                }
            )

        max_density = max(r["_density"] for r in hotspot_rows) or 1.0
        for r in hotspot_rows:
            normalized_density = r["_density"] / max_density
            r["risk_score"] = round(
                normalized_density * r["avg_severity"] / MAX_SEVERITY, 4
            )
            del r["_density"]

        hotspot_rows.sort(key=lambda r: r["risk_score"], reverse=True)

        # Assign stable sequential ids sorted by risk (optional but nicer to read).
        for i, r in enumerate(hotspot_rows):
            r["cluster_id"] = i

        self.hotspots_ = hotspot_rows
        return hotspot_rows

    def add_cluster_labels(self, df: pd.DataFrame) -> pd.DataFrame:
        """Attach a ``cluster`` column to an input DataFrame.

        Rows already considered during :meth:`fit_predict` (matched by rounded
        coordinates) receive their learned label; new/unmatched rows receive ``-1``.
        """
        if self.labels_ is None or self._fitted_df is None:
            raise RuntimeError("No fitted clusters - call fit_predict() first")

        out = df.copy()
        lat_col = _resolve_column(out, LAT_COLS, "latitude")
        lon_col = _resolve_column(out, LON_COLS, "longitude")

        fitted = self._fitted_df.copy()
        fitted["_cluster"] = self.labels_
        fitted["_hkey"] = list(
            zip(
                np.round(fitted[self._lat_col].to_numpy(float), 5),
                np.round(fitted[self._lon_col].to_numpy(float), 5),
            )
        )
        lookup = dict(zip(fitted["_hkey"], fitted["_cluster"]))

        out["_hkey"] = list(
            zip(
                np.round(out[lat_col].to_numpy(float), 5),
                np.round(out[lon_col].to_numpy(float), 5),
            )
        )
        out["cluster"] = out["_hkey"].map(lookup).fillna(-1).astype(int)
        return out.drop(columns=["_hkey"])

    # ------------------------------------------------------------- visualize
    def visualize_clusters(self, save_path: Optional[Union[str, Path]] = None):
        """Render a matplotlib scatter of events coloured by cluster.

        Noise points are drawn in grey, hotspots are annotated with their risk
        score.  Returns the ``matplotlib.figure.Figure`` and optionally saves it to
        ``save_path``.
        """
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        if self.labels_ is None or self._fitted_df is None:
            raise RuntimeError("No fitted clusters - call fit_predict() first")

        df = self._fitted_df.copy()
        df["_cluster"] = self.labels_
        hotspots = self.get_hotspots()

        fig, ax = plt.subplots(figsize=(10, 7))
        ax.set_aspect("equal")
        ax.set_title("Crisis event clusters (HDBSCAN)")
        ax.set_xlabel("Longitude")
        ax.set_ylabel("Latitude")

        noise = df[df["_cluster"] < 0]
        if not noise.empty:
            ax.scatter(
                noise[self._lon_col], noise[self._lat_col],
                c="lightgrey", s=8, marker=".", label="noise",
            )

        clusters = df[df["_cluster"] >= 0]
        if not clusters.empty:
            scatter = ax.scatter(
                clusters[self._lon_col], clusters[self._lat_col],
                c=clusters["_cluster"], cmap="tab20", s=25, edgecolors="none",
            )
            fig.colorbar(scatter, ax=ax, label="cluster id")

        for h in hotspots:
            ax.annotate(
                f"risk={h['risk_score']:.3f}",
                (h["center_lon"], h["center_lat"]),
                textcoords="offset points",
                xytext=(5, 5),
                fontsize=8,
                color="darkred",
            )
        ax.legend(loc="best")
        fig.tight_layout()

        if save_path:
            dest = Path(save_path)
            dest.parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(dest, dpi=140, bbox_inches="tight")
            logger.info("Saved cluster plot to %s", dest)
        return fig

    # -------------------------------------------------------- persistence
    def save_hotspots(self, path: Optional[Union[str, Path]] = None) -> Path:
        """Persist the hotspot summaries as a CSV."""
        if not self.hotspots_:
            self.get_hotspots()
        dest = Path(path) if path else HOTSPOTS_PATH.with_suffix(".csv")
        dest.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(self.hotspots_).to_csv(dest, index=False)
        return dest

    # --------------------------------------------------------------- helpers
    @staticmethod
    def _approx_area_km2(lats: np.ndarray, lons: np.ndarray) -> float:
        """Bounding-box surface area of a point set in square kilometres."""
        if len(lats) < 2:
            return 1.0
        lat0, lat1 = float(np.min(lats)), float(np.max(lats))
        lon0, lon1 = float(np.min(lons)), float(np.max(lons))
        if lat1 == lat0 and lon1 == lon0:
            return 1.0
        r = EARTH_RADIUS_KM
        lat_span = abs(lat1 - lat0) * np.pi / 180.0 * r
        mean_lat = (lat0 + lat1) / 2.0 * np.pi / 180.0
        lon_span = abs(lon1 - lon0) * np.pi / 180.0 * r * np.cos(mean_lat)
        return max(lat_span * lon_span, 1.0)


__all__ = ["CrisisClustering", "HOTSPOTS_PATH"]