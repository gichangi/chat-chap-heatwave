from __future__ import annotations
import subprocess, sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "example_data"

def _run(args, check=True):
    return subprocess.run([sys.executable, *args], cwd=ROOT, check=check, capture_output=True, text=True)

def test_train_predict_preserves_organization_units_and_returns_binary_flags(tmp_path):
    config = tmp_path / "config.yml"
    config.write_text("threshold_percentile: 90\npooling_window_weeks: 1\nmin_baseline_observations: 3\nn_samples: 12\n")
    model = tmp_path / "climatology.pickle"; output = tmp_path / "predictions.csv"
    _run(["scripts/train_model.py", "--data", str(EXAMPLE / "historic_data.csv"), "--model", str(model), "--config", str(config)])
    _run(["scripts/predict_model.py", "--historic", str(EXAMPLE / "historic_data.csv"), "--future", str(EXAMPLE / "future_data.csv"), "--model", str(model), "--output", str(output), "--config", str(config)])
    result = pd.read_csv(output); future = pd.read_csv(EXAMPLE / "future_data.csv")
    assert len(result) == len(future)
    assert result["location"].tolist() == future["location"].astype(str).tolist()
    assert len(result.filter(like="sample_").columns) == 12
    assert set(result.filter(like="sample_").stack().unique()) <= {0, 1}
    assert result.notna().all().all()

def test_organization_unit_alias_and_strict_exceedance_rule():
    sys.path.insert(0, str(ROOT / "scripts"))
    from heat_features import classify_heatwave_weeks, fit_climatology
    baseline = pd.DataFrame({"time_period": ["2020-W01", "2021-W01", "2022-W01"] * 2,
        "organization_unit": ["ward-a"] * 3 + ["ward-b"] * 3,
        "max_heat_index": [90, 100, 110, 70, 80, 90]})
    artifact = fit_climatology(baseline, percentile=50, pooling_window_weeks=0, min_baseline_observations=3)
    future = pd.DataFrame({"time_period": ["2023-W01", "2023-W01", "2024-W01"],
        "organization_unit": ["ward-a", "ward-b", "ward-a"], "max_heat_index": [101, 80, 100]})
    result = classify_heatwave_weeks(future, artifact)
    assert result["location"].tolist() == ["ward-a", "ward-b", "ward-a"]
    assert result["climatological_threshold"].tolist() == [100, 80, 100]
    assert result["heatwave"].tolist() == [1, 0, 0]

def test_unknown_organization_unit_is_rejected(tmp_path):
    config = tmp_path / "config.yml"; config.write_text("min_baseline_observations: 3\n")
    model = tmp_path / "model.pickle"
    _run(["scripts/train_model.py", "--data", str(EXAMPLE / "historic_data.csv"), "--model", str(model), "--config", str(config)])
    future = pd.read_csv(EXAMPLE / "future_data.csv").head(1); future["location"] = "unknown-ward"; path = tmp_path / "future.csv"; future.to_csv(path, index=False)
    failed = _run(["scripts/predict_model.py", "--historic", str(EXAMPLE / "historic_data.csv"), "--future", str(path), "--model", str(model), "--output", str(tmp_path / "out.csv"), "--config", str(config)], check=False)
    assert failed.returncode != 0
    assert "organization units absent from the climatology" in failed.stderr
