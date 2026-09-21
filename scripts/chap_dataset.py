"""Build and validate CHAP heatwave datasets from weekly ward covariates.

This module is deliberately pandas-only and safe to run without Earth Engine.
CHAP's current weekly generator uses the ISO-like ``YYYY-Www`` form, which is
also accepted by chap-core's weekly period parser.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import pandas as pd

KEY_COLUMNS = ["time_period", "location"]
HEAT_COLUMNS = ["heatwave_days", "mean_heat_index", "max_heat_index", "heatwave_event_count"]
TARGET_COLUMN = "heatwave"
OUTPUT_COLUMNS = [*KEY_COLUMNS, TARGET_COLUMN, *HEAT_COLUMNS]
COVARIATE_COLUMNS = [*KEY_COLUMNS, *HEAT_COLUMNS]
PERIOD_RE = re.compile(r"^(\d{4})-?W(\d{1,2})$")


def normalize_period(value: object) -> str:
    """Normalize a supported weekly period to CHAP's ``YYYY-Www`` form."""
    text = str(value).strip()
    match = PERIOD_RE.fullmatch(text)
    if not match:
        raise ValueError(f"invalid weekly time_period {text!r}; expected YYYY-Www")
    year, week = map(int, match.groups())
    try:
        pd.Timestamp.fromisocalendar(year, week, 1)
    except ValueError as error:
        raise ValueError(f"invalid ISO week {text!r}") from error
    return f"{year:04d}-W{week:02d}"


def _require(frame: pd.DataFrame, columns: list[str], source: str) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"{source} is missing required columns: {', '.join(missing)}")


def _normalize_keys(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["time_period"] = result["time_period"].map(normalize_period)
    result["location"] = result["location"].astype(str)
    return result


def _apply_crosswalk(covariates: pd.DataFrame, crosswalk: pd.DataFrame) -> pd.DataFrame:
    _require(crosswalk, ["ward_id", "location"], "crosswalk")
    if crosswalk["ward_id"].duplicated().any():
        raise ValueError("crosswalk contains duplicate ward_id values")
    mapped = covariates.rename(columns={"location": "ward_id"}).merge(
        crosswalk[["ward_id", "location"]].astype(str), on="ward_id", how="left", validate="many_to_one"
    )
    if mapped["location"].isna().any():
        wards = sorted(mapped.loc[mapped["location"].isna(), "ward_id"].unique())
        raise ValueError(f"crosswalk has no target location for wards: {', '.join(wards[:10])}")
    return mapped.groupby(KEY_COLUMNS, as_index=False).agg(
        heatwave_days=("heatwave_days", "mean"),
        mean_heat_index=("mean_heat_index", "mean"),
        max_heat_index=("max_heat_index", "max"),
        heatwave_event_count=("heatwave_event_count", "mean"),
    )


def build_dataset(covariates: pd.DataFrame,
                  crosswalk: pd.DataFrame | None = None) -> tuple[pd.DataFrame, pd.DataFrame | None]:
    _require(covariates, COVARIATE_COLUMNS, "covariates")
    covariates = _normalize_keys(covariates)
    qa_columns = [column for column in covariates.columns if column not in COVARIATE_COLUMNS]
    qa = covariates[[*KEY_COLUMNS, *qa_columns]].copy() if qa_columns else None
    covariates = covariates[COVARIATE_COLUMNS]
    if crosswalk is not None:
        covariates = _apply_crosswalk(covariates, crosswalk)
        if qa is not None:
            qa = qa.rename(columns={"location": "ward_id"}).merge(
                crosswalk[["ward_id", "location"]].astype(str), on="ward_id", how="left"
            )
    if covariates.duplicated(KEY_COLUMNS).any():
        raise ValueError("covariates contain duplicate (time_period, location) rows")
    result = covariates.copy()
    result[TARGET_COLUMN] = (result["heatwave_days"] > 0).astype(int)
    return result[OUTPUT_COLUMNS], qa


def _geojson_locations(path: str | Path) -> set[str]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    locations: set[str] = set()
    for feature in payload.get("features", []):
        properties = feature.get("properties") or {}
        value = next((properties.get(key) for key in ("id", "location", "uid", "ward_id") if properties.get(key) is not None), feature.get("id"))
        if value is None:
            raise ValueError("every GeoJSON feature must have an id or id/location/uid/ward_id property")
        locations.add(str(value))
    return locations


def validate_dataset(frame: pd.DataFrame, geojson: str | Path, strict: bool = False) -> list[str]:
    errors: list[str] = []
    try:
        _require(frame, OUTPUT_COLUMNS, "dataset")
    except ValueError as error:
        return [str(error)]
    if frame.duplicated(KEY_COLUMNS).any():
        errors.append("duplicate (time_period, location) rows")
    normalized: list[str] = []
    for value in frame["time_period"]:
        try:
            period = normalize_period(value)
            normalized.append(period)
            if str(value) != period:
                errors.append(f"non-canonical weekly time_period: {value}")
        except ValueError as error:
            errors.append(str(error))
    data_locations = set(frame["location"].astype(str))
    geo_locations = _geojson_locations(geojson)
    only_data, only_geo = sorted(data_locations - geo_locations), sorted(geo_locations - data_locations)
    if only_data:
        errors.append("locations absent from GeoJSON: " + ", ".join(only_data))
    if only_geo:
        errors.append("GeoJSON locations absent from dataset: " + ", ".join(only_geo))
    if len(normalized) == len(frame):
        work = frame.assign(_monday=[pd.Timestamp.fromisocalendar(int(p[:4]), int(p[-2:]), 1) for p in normalized])
        for location, group in work.groupby("location"):
            dates = group["_monday"].drop_duplicates().sort_values()
            if len(dates) > 1 and not dates.diff().dropna().eq(pd.Timedelta(days=7)).all():
                errors.append(f"weekly grid has gaps for location {location}")
    missing = frame[HEAT_COLUMNS].isna().mean()
    for column, fraction in missing.items():
        print(f"{column}: missing fraction {fraction:.2%}", file=sys.stderr)
        if strict and fraction > 0:
            errors.append(f"strict validation: {column} has missing values ({fraction:.2%})")
    return list(dict.fromkeys(errors))


def _build_command(args: argparse.Namespace) -> int:
    covariates = pd.read_csv(args.covariates)
    crosswalk = pd.read_csv(args.crosswalk, dtype=str) if args.crosswalk else None
    result, qa = build_dataset(covariates, crosswalk)
    out = Path(args.out); out.parent.mkdir(parents=True, exist_ok=True); result.to_csv(out, index=False)
    for column, fraction in result[HEAT_COLUMNS].isna().mean().items():
        print(f"{column}: missing fraction {fraction:.2%}", file=sys.stderr)
    if qa is not None:
        qa.to_csv(Path(str(out) + ".qa.csv"), index=False)
    return 0


def _validate_command(args: argparse.Namespace) -> int:
    errors = validate_dataset(pd.read_csv(args.dataset), args.geojson, args.strict)
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    return 1 if errors else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__); sub = parser.add_subparsers(required=True)
    build = sub.add_parser("build"); build.add_argument("--covariates", required=True); build.add_argument("--geojson"); build.add_argument("--crosswalk"); build.add_argument("--out", required=True); build.set_defaults(run=_build_command)
    validate = sub.add_parser("validate"); validate.add_argument("--dataset", required=True); validate.add_argument("--geojson", required=True); validate.add_argument("--strict", action="store_true"); validate.set_defaults(run=_validate_command)
    args = parser.parse_args(argv)
    try:
        return args.run(args)
    except (ValueError, OSError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr); return 1


if __name__ == "__main__":
    raise SystemExit(main())

