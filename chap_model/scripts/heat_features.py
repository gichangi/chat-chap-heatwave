"""Ward-specific weekly Heat Index climatology helpers."""
from __future__ import annotations
import re
import numpy as np
import pandas as pd

PERIOD_RE = re.compile(r"^(\d{4})-?W(\d{1,2})$")
ORG_UNIT_ALIASES = ("organization_unit", "organisation_unit", "org_unit", "ward_id")

def parse_period(value: object) -> tuple[int, int]:
    match = PERIOD_RE.fullmatch(str(value).strip())
    if not match: raise ValueError(f"invalid weekly period {value!r}; expected YYYY-Www")
    year, week = map(int, match.groups())
    try: pd.Timestamp.fromisocalendar(year, week, 1)
    except ValueError as error: raise ValueError(f"invalid ISO week {value!r}") from error
    return year, week

def normalize_period(value: object) -> str:
    year, week = parse_period(value); return f"{year:04d}-W{week:02d}"

def normalize_organization_units(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize a DHIS2 organization-unit column to CHAP's `location`."""
    result = frame.copy()
    if "location" not in result:
        matches = [name for name in ORG_UNIT_ALIASES if name in result]
        if len(matches) != 1:
            raise ValueError("data must contain location or exactly one organization-unit column: " + ", ".join(ORG_UNIT_ALIASES))
        result = result.rename(columns={matches[0]: "location"})
    if result["location"].isna().any() or (result["location"].astype(str).str.strip() == "").any():
        raise ValueError("organization-unit identifiers cannot be empty")
    result["location"] = result["location"].astype(str)
    return result

def prepare_heat_index(frame: pd.DataFrame) -> pd.DataFrame:
    result = normalize_organization_units(frame)
    missing = [name for name in ("time_period", "max_heat_index") if name not in result]
    if missing: raise ValueError("data is missing columns: " + ", ".join(missing))
    result["time_period"] = result["time_period"].map(normalize_period)
    result["iso_week"] = result["time_period"].map(lambda value: parse_period(value)[1])
    result["max_heat_index"] = pd.to_numeric(result["max_heat_index"], errors="coerce")
    if result["max_heat_index"].isna().any(): raise ValueError("max_heat_index must contain a value for every organization unit and week")
    return result

def _week_distance(weeks: pd.Series, week: int) -> pd.Series:
    delta = (weeks.astype(int) - week).abs(); return np.minimum(delta, 53 - delta)

def fit_climatology(frame: pd.DataFrame, percentile: float = 90, pooling_window_weeks: int = 1, min_baseline_observations: int = 3) -> dict:
    data = prepare_heat_index(frame); thresholds: dict[str, dict[int, float]] = {}
    for location, group in data.groupby("location", sort=True):
        by_week = {}
        for week in range(1, 54):
            pooled = group.loc[_week_distance(group["iso_week"], week) <= pooling_window_weeks, "max_heat_index"]
            if len(pooled) >= min_baseline_observations: by_week[week] = float(np.percentile(pooled.to_numpy(), percentile))
        if not by_week: raise ValueError(f"organization unit {location!r} has insufficient climatology observations")
        thresholds[str(location)] = by_week
    return {"thresholds": thresholds, "percentile": float(percentile), "pooling_window_weeks": int(pooling_window_weeks), "min_baseline_observations": int(min_baseline_observations)}

def classify_heatwave_weeks(frame: pd.DataFrame, artifact: dict) -> pd.DataFrame:
    data = prepare_heat_index(frame)
    unknown = sorted(set(data["location"]) - set(artifact["thresholds"]))
    if unknown: raise ValueError("future data contains organization units absent from the climatology: " + ", ".join(unknown))
    def threshold_for(row: pd.Series) -> float:
        thresholds = artifact["thresholds"][row["location"]]; week = int(row["iso_week"])
        if week in thresholds: return thresholds[week]
        nearest = min(thresholds, key=lambda candidate: min(abs(candidate-week), 53-abs(candidate-week)))
        return thresholds[nearest]
    output = data[["time_period", "location", "max_heat_index"]].copy()
    output["climatological_threshold"] = data.apply(threshold_for, axis=1)
    output["heatwave"] = (output["max_heat_index"] > output["climatological_threshold"]).astype(int)
    return output
