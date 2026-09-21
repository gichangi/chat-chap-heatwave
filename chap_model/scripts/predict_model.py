from __future__ import annotations
import argparse, os, pickle, sys
from pathlib import Path
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np, pandas as pd, yaml
from heat_features import HEAT_COLUMNS, build_features, load_heat_covariates, normalize_period

def _load_config(path: str) -> dict:
    config_path = Path(path)
    config = yaml.safe_load(config_path.read_text()) if config_path.exists() else {}
    return config.get("user_option_values", config) if config else {}

def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument("--historic",required=True); parser.add_argument("--future",required=True); parser.add_argument("--model",default="model.pickle"); parser.add_argument("--output",required=True); parser.add_argument("--config",default="config.yml"); parser.add_argument("--geo"); args=parser.parse_args()
    config=_load_config(args.config)
    with Path(args.model).open("rb") as stream: artifact=pickle.load(stream)
    historic,future=pd.read_csv(args.historic),pd.read_csv(args.future); historic["time_period"]=historic["time_period"].map(normalize_period); future["time_period"]=future["time_period"].map(normalize_period)
    unknown=sorted(set(future["location"].astype(str))-set(artifact["trained_locations"]));
    if unknown: raise ValueError("future data contains locations absent from training: "+", ".join(unknown))
    horizon=int(future.groupby("location").size().max()) if len(future) else 0; lag=int(artifact["heat_lag_weeks"])
    if horizon>lag: raise ValueError(f"prediction horizon {horizon} exceeds heat_lag_weeks={lag}")
    historic=load_heat_covariates(historic)
    for column in HEAT_COLUMNS: future[column]=np.nan
    featured,_=build_features(pd.concat([historic,future],ignore_index=True,sort=False),lag); future_keys=set(zip(future["time_period"],future["location"].astype(str)))
    rows=featured[[ (str(p),str(loc)) in future_keys for p,loc in zip(featured.time_period,featured.location)]].sort_values(["location","_monday"]); features=artifact["feature_columns"]
    if rows[features].isna().any().any(): raise ValueError("future features contain missing values; check historic heat coverage and future climate covariates")
    means=artifact["estimator"].predict(rows[features]); rng=np.random.default_rng(int(config.get("random_seed",42))); n=int(config.get("n_samples",100)); residuals=np.asarray(artifact["residuals"])
    samples=np.maximum(0.0,means[:,None]+rng.choice(residuals,size=(len(means),n),replace=True)); output=rows[["time_period","location"]].reset_index(drop=True)
    output=pd.concat([output,pd.DataFrame(samples,columns=[f"sample_{i}" for i in range(n)])],axis=1)
    if len(output)!=len(future) or output.isna().any().any(): raise AssertionError("prediction output violates the CHAP row/NaN contract")
    output.to_csv(args.output,index=False)
if __name__=="__main__": main()

