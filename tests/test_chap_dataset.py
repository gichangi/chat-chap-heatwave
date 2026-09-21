import json
import pandas as pd
import pytest
from scripts.chap_dataset import HEAT_COLUMNS, OUTPUT_COLUMNS, build_dataset, normalize_period, validate_dataset


def _health(periods=("2020-W53", "2021-W01"), locations=("A",)):
    return pd.DataFrame([{"time_period": p, "location": loc, "disease_cases": 2, "population": 100, "rainfall": 4, "mean_temperature": 25} for loc in locations for p in periods])


def _heat():
    return pd.DataFrame([{"time_period": "2020W53", "location": "w1", "heatwave_days": 2, "mean_heat_index": 90, "max_heat_index": 100, "heatwave_event_count": 1, "used_fallback_reducer": False}, {"time_period": "2020-W53", "location": "w2", "heatwave_days": 4, "mean_heat_index": 94, "max_heat_index": 105, "heatwave_event_count": 3, "used_fallback_reducer": True}])


def _geo(locations):
    path = __import__("pathlib").Path(".test-units.geojson")
    path.write_text(json.dumps({"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"id": loc}, "geometry": None} for loc in locations]}))
    return path


def test_period_normalization_handles_iso_year_edges():
    assert normalize_period("2020W53") == "2020-W53"
    assert normalize_period("2021-W1") == "2021-W01"
    with pytest.raises(ValueError): normalize_period("2021-W53")


def test_build_aggregates_crosswalk_and_preserves_missing():
    crosswalk = pd.DataFrame({"ward_id": ["w1", "w2"], "location": ["A", "A"]})
    result, qa = build_dataset(_heat(), _health(), crosswalk)
    assert list(result.columns) == OUTPUT_COLUMNS
    first = result.iloc[0]
    assert first["heatwave_days"] == 3 and first["mean_heat_index"] == 92
    assert first["max_heat_index"] == 105 and first["heatwave_event_count"] == 2
    assert result.iloc[1][HEAT_COLUMNS].isna().all()
    assert qa is not None and "used_fallback_reducer" in qa


def test_validate_reports_duplicate_gap_geo_mismatch_and_strict_missing():
    frame = _health(periods=("2021-W01", "2021-W03"), locations=("A",)).assign(**{column: 1.0 for column in HEAT_COLUMNS})
    frame = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)
    frame.loc[0, "mean_heat_index"] = None
    path = _geo(["B"])
    try:
        errors = validate_dataset(frame, path, strict=True)
    finally:
        path.unlink(missing_ok=True)
    assert any("duplicate" in error for error in errors)
    assert any("gaps" in error for error in errors)
    assert any("absent from GeoJSON" in error for error in errors)
    assert any("absent from dataset" in error for error in errors)
    assert any("strict validation" in error for error in errors)
