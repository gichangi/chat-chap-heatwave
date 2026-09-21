from __future__ import annotations
import argparse, os, pickle, sys
from pathlib import Path
sys.path.insert(0, os.path.dirname(__file__))
import pandas as pd, yaml
from sklearn.ensemble import RandomForestRegressor
from heat_features import build_features, load_heat_covariates

def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument("--data",required=True); parser.add_argument("--geo"); args=parser.parse_args()
    config=yaml.safe_load(Path("config.yml").read_text()) if Path("config.yml").exists() else {}
    lag=int(config.get("heat_lag_weeks",4)); data=load_heat_covariates(pd.read_csv(args.data)); featured,features=build_features(data,lag)
    usable=featured.dropna(subset=[*features,"disease_cases"])
    if len(usable)<30: raise ValueError(f"at least 30 usable training rows are required after lagging; got {len(usable)}")
    estimator=RandomForestRegressor(n_estimators=int(config.get("n_estimators",200)),min_samples_leaf=3,random_state=int(config.get("random_seed",42)),n_jobs=1)
    estimator.fit(usable[features],usable["disease_cases"]); residuals=usable["disease_cases"].to_numpy()-estimator.predict(usable[features])
    with Path("model.pickle").open("wb") as stream: pickle.dump({"estimator":estimator,"residuals":residuals,"feature_columns":features,"heat_lag_weeks":lag,"trained_locations":sorted(data["location"].astype(str).unique())},stream)
if __name__=="__main__": main()

