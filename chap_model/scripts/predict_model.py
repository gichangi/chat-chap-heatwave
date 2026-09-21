from __future__ import annotations
import argparse, os, pickle, sys
from pathlib import Path
sys.path.insert(0, os.path.dirname(__file__))
import pandas as pd, yaml
from heat_features import classify_heatwave_weeks

def _load_config(path: str) -> dict:
    p=Path(path); config=yaml.safe_load(p.read_text()) if p.exists() else {}
    return config.get("user_option_values", config) if config else {}

def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument("--historic",required=True); parser.add_argument("--future",required=True); parser.add_argument("--model",default="model.pickle"); parser.add_argument("--output",required=True); parser.add_argument("--config",default="config.yml"); parser.add_argument("--geo"); args=parser.parse_args(); config=_load_config(args.config)
    with Path(args.model).open("rb") as stream: artifact=pickle.load(stream)
    classified=classify_heatwave_weeks(pd.read_csv(args.future),artifact); n=int(config.get("n_samples",100)); output=classified[["time_period","location"]].copy()
    for index in range(n): output[f"sample_{index}"]=classified["heatwave"].to_numpy()
    if len(output)!=len(classified) or output.isna().any().any(): raise AssertionError("prediction output violates the CHAP row/NaN contract")
    output.to_csv(args.output,index=False)
if __name__=="__main__": main()
