from __future__ import annotations
import argparse, os, pickle, sys
from pathlib import Path
sys.path.insert(0, os.path.dirname(__file__))
import pandas as pd, yaml
from heat_features import fit_climatology

def _load_config(path: str) -> dict:
    p=Path(path); config=yaml.safe_load(p.read_text()) if p.exists() else {}
    return config.get("user_option_values", config) if config else {}

def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument("--data",required=True); parser.add_argument("--model",default="model.pickle"); parser.add_argument("--config",default="config.yml"); parser.add_argument("--geo"); args=parser.parse_args(); config=_load_config(args.config)
    artifact=fit_climatology(pd.read_csv(args.data),float(config.get("threshold_percentile",90)),int(config.get("pooling_window_weeks",1)),int(config.get("min_baseline_observations",3)))
    with Path(args.model).open("wb") as stream: pickle.dump(artifact,stream)
if __name__=="__main__": main()
