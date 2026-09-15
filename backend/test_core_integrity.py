"""Core integrity unit tests for CrisisWatchAI backend."""
from datetime import datetime, timezone
import numpy as np
import pandas as pd

from data.preprocessing import _dedup_key
from data.schema import CrisisEvent
from data.sources.nasa_firms import NASAFIRMSSource
from data.sources.usgs import USGSSource
from ml.forecaster import CrisisForecaster


def test_usgs_felt_reports_not_casualties():
    source = USGSSource()
    feature = {
        "id": "us7000test",
        "properties": {
            "mag": 6.2,
            "place": "10 km N of Test City, Country",
            "time": 1700000000000,
            "felt": 1250,  # 1250 felt reports
            "alert": "green",
        },
        "geometry": {
            "coordinates": [140.0, 37.0, 10.0]
        },
    }
    event = source._parse_feature(feature)
    assert event is not None
    assert event.casualties is None, "Felt shaking reports must not be parsed as verified casualties"
    assert event.metadata.get("felt") == 1250, "Felt reports should be stored in metadata['felt']"


def test_nasa_firms_affected_none():
    source = NASAFIRMSSource()
    row = {
        "latitude": "37.5",
        "longitude": "-120.2",
        "confidence": "high",
        "frp": "120.5",
        "acq_date": "2026-09-15",
        "acq_time": "1200",
        "satellite": "N",
        "instrument": "VIIRS",
    }
    event = source._parse_row(row)
    assert event is not None
    assert event.affected is None, "Satellite thermal anomaly must not assume 1 affected person without ground data"


def test_dedup_key_coordinateless_boundary():
    event_a = CrisisEvent(
        source="test",
        event_type="flood",
        title="Flooding in Dhaka",
        description="Heavy rain",
        severity=3,
        latitude=float("nan"),
        longitude=float("nan"),
        country="Bangladesh",
        region="Dhaka",
        timestamp=datetime(2026, 9, 15, tzinfo=timezone.utc),
    )
    event_b = CrisisEvent(
        source="test",
        event_type="flood",
        title="Flooding in Madrid",
        description="Heavy rain",
        severity=3,
        latitude=float("nan"),
        longitude=float("nan"),
        country="Spain",
        region="Madrid",
        timestamp=datetime(2026, 9, 15, tzinfo=timezone.utc),
    )
    key_a = _dedup_key(event_a)
    key_b = _dedup_key(event_b)
    assert key_a != key_b, "Coordinateless events in different countries/regions must not produce the same dedup key"


def test_forecaster_naive_future_dates():
    df = pd.DataFrame({
        "ds": pd.date_range("2026-01-01", periods=10, freq="D"),
        "y": [5, 6, 5, 7, 8, 6, 7, 8, 9, 10],
    })
    fc = CrisisForecaster()
    fc._train_naive(df)
    fc_pred = fc._predict_naive(periods=5, freq="D")
    
    assert len(fc_pred) == 5
    assert fc_pred["ds"].min() > df["ds"].max(), "Forecast dates must start after the last training observation"
    assert (fc_pred["yhat"] >= 0).all(), "Predictions must be non-negative"


if __name__ == "__main__":
    test_usgs_felt_reports_not_casualties()
    test_nasa_firms_affected_none()
    test_dedup_key_coordinateless_boundary()
    test_forecaster_naive_future_dates()
    print("All core integrity unit tests passed!")
