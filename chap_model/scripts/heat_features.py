"""Shared, credential-free heat feature preparation."""
from __future__ import annotations
import os, re
from pathlib import Path
import numpy as np
import pandas as pd

HEAT_COLUMNS = ["heatwave_days", "mean_heat_index", "max_heat_index", "heatwave_event_count"]
BASE_FEATURES = ["rainfall", "mean_temperature"]
PERIOD_RE = re.compile(r"^(\d{4})-?W(\d{1,2})$")

def parse_period(value: object) -> tuple[int, int]:
    match = PERIOD_RE.fullmatch(str(value).strip())
    if not match: raise ValueError(f"invalid weekly period {value!r}; expected YYYY-Www")
    year, week = map(int, match.groups())
    try: pd.Timestamp.fromisocalendar(year, week, 1)
    except ValueError as error: raise ValueError(f"invalid ISO week {value!r}") from error
    return year, week

def normalize_period(value: object) -> str:
    year, week = parse_period(value); return f"{year:04d}-W{week:02d}"

def load_heat_covariates(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy(); result["time_period"] = result["time_period"].map(normalize_period)
    if all(column in result.columns for column in HEAT_COLUMNS): return result
    sidecar_path = os.getenv("HEATWAVE_COVARIATE_TABLE")
    if not sidecar_path: raise ValueError("heat covariates are required: include all four heat columns or set HEATWAVE_COVARIATE_TABLE")
    sidecar = pd.read_csv(Path(sidecar_path))
    missing = [c for c in ["time_period", "location", *HEAT_COLUMNS] if c not in sidecar]
    if missing: raise ValueError("HEATWAVE_COVARIATE_TABLE is missing columns: " + ", ".join(missing))
    sidecar["time_period"] = sidecar["time_period"].map(normalize_period)
    return result.drop(columns=[c for c in HEAT_COLUMNS if c in result], errors="ignore").merge(
        sidecar[["time_period", "location", *HEAT_COLUMNS]], on=["time_period", "location"], how="left", validate="one_to_one")

def build_features(frame: pd.DataFrame, heat_lag_weeks: int) -> tuple[pd.DataFrame, list[str]]:
    required = ["time_period", "location", *BASE_FEATURES, *HEAT_COLUMNS]
    missing = [c for c in required if c not in frame]
    if missing: raise ValueError("data is missing feature columns: " + ", ".join(missing))
    result = frame.copy(); result["time_period"] = result["time_period"].map(normalize_period)
    result["_monday"] = [pd.Timestamp.fromisocalendar(*parse_period(v), 1) for v in result["time_period"]]
    result = result.sort_values(["location", "_monday"]).copy(); lagged = []
    for column in HEAT_COLUMNS:
        name = f"{column}_lag_{heat_lag_weeks}"; result[name] = result.groupby("location", sort=False)[column].shift(heat_lag_weeks); lagged.append(name)
    weeks = result["time_period"].map(lambda v: parse_period(v)[1]).astype(float)
    result["week_sin"] = np.sin(2*np.pi*weeks/52.1775); result["week_cos"] = np.cos(2*np.pi*weeks/52.1775)
    return result, [*BASE_FEATURES, *lagged, "week_sin", "week_cos"]

