from __future__ import annotations
import os, shutil, subprocess, sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "example_data"
ARTIFACTS = ROOT / ".test-artifacts"


def _run(args, env=None, check=True):
    return subprocess.run([sys.executable, *args], cwd=ROOT, env=env, check=check, capture_output=True, text=True)


def _prepare():
    if ARTIFACTS.exists(): shutil.rmtree(ARTIFACTS)
    ARTIFACTS.mkdir()
    (ROOT / "config.yml").write_text("heat_lag_weeks: 4\nn_samples: 100\nrandom_seed: 42\nn_estimators: 40\n")


def test_train_predict_and_horizon_guard():
    _prepare()
    _run(["scripts/train_model.py", "--data", str(EXAMPLE / "historic_data.csv")])
    output = ARTIFACTS / "predictions.csv"
    _run(["scripts/predict_model.py", "--historic", str(EXAMPLE / "historic_data.csv"), "--future", str(EXAMPLE / "future_data.csv"), "--output", str(output)])
    result = pd.read_csv(output)
    assert len(result) == 24 and list(result.columns[:2]) == ["time_period", "location"]
    assert len(result.filter(like="sample_").columns) == 100
    assert result.notna().all().all() and (result.filter(like="sample_") >= 0).all().all()
    future = pd.read_csv(EXAMPLE / "future_data.csv")
    fifth = future.groupby("location", group_keys=False).tail(1).copy()
    fifth["time_period"] = "2024-W06"
    too_long = pd.concat([future, fifth], ignore_index=True); too_long.to_csv(ARTIFACTS / "too_long.csv", index=False)
    failed = _run(["scripts/predict_model.py", "--historic", str(EXAMPLE / "historic_data.csv"), "--future", str(ARTIFACTS / "too_long.csv"), "--output", str(output)], check=False)
    assert failed.returncode != 0 and "exceeds heat_lag_weeks" in failed.stderr


def test_sidecar_mode():
    _prepare(); historic = pd.read_csv(EXAMPLE / "historic_data.csv"); heat = historic[["time_period", "location", "heatwave_days", "mean_heat_index", "max_heat_index", "heatwave_event_count"]]
    heat.to_csv(ARTIFACTS / "heat.csv", index=False); historic.drop(columns=["heatwave_days", "mean_heat_index", "max_heat_index", "heatwave_event_count"]).to_csv(ARTIFACTS / "historic.csv", index=False)
    env = os.environ.copy(); env["HEATWAVE_COVARIATE_TABLE"] = str(ARTIFACTS / "heat.csv")
    _run(["scripts/train_model.py", "--data", str(ARTIFACTS / "historic.csv")], env=env)
    _run(["scripts/predict_model.py", "--historic", str(ARTIFACTS / "historic.csv"), "--future", str(EXAMPLE / "future_data.csv"), "--output", str(ARTIFACTS / "sidecar_predictions.csv")], env=env)
    assert len(pd.read_csv(ARTIFACTS / "sidecar_predictions.csv")) == 24

