"""Chapkit service for ward-specific Heat Index threshold detection."""
import os
from pathlib import Path
from chapkit import BaseConfig
from chapkit.api import AssessedStatus, MLServiceBuilder, MLServiceInfo, ModelMetadata, PeriodType
from chapkit.artifact import ArtifactHierarchy
from chapkit.ml import ShellModelRunner
from pydantic import Field

class HeatwaveModelConfig(BaseConfig):
    prediction_periods: int = 1
    threshold_percentile: float = Field(default=90, ge=0, le=100)
    pooling_window_weeks: int = Field(default=1, ge=0, le=26)
    min_baseline_observations: int = Field(default=3, ge=1)
    n_samples: int = Field(default=100, ge=1)

runner: ShellModelRunner[HeatwaveModelConfig] = ShellModelRunner(
    train_command="python scripts/train_model.py --data {data_file}",
    predict_command="python scripts/predict_model.py --historic {historic_file} --future {future_file} --output {output_file}",
)
info = MLServiceInfo(
    id="ward-heatwave-threshold-model", display_name="Ward heatwave threshold model", version="0.2.0",
    description=("Experimental weekly detector that preserves each organization unit and flags maximum Heat Index "
                 "values above that ward's own seasonal climatological threshold. Heat Index is in degrees Fahrenheit."),
    model_metadata=ModelMetadata(author="gichangi", author_assessed_status=AssessedStatus.red),
    period_type=PeriodType.weekly, required_covariates=["max_heat_index"], min_prediction_periods=1, max_prediction_periods=52,
)
HIERARCHY = ArtifactHierarchy(name="heatwave_covariate_model", level_labels={0: "ml_training_workspace", 1: "ml_prediction"})
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///data/chapkit.db")
if DATABASE_URL.startswith("sqlite") and ":///" in DATABASE_URL:
    Path(DATABASE_URL.split("///")[1]).parent.mkdir(parents=True, exist_ok=True)
app = (MLServiceBuilder(info=info, config_schema=HeatwaveModelConfig, hierarchy=HIERARCHY,
                        runner=runner, database_url=DATABASE_URL).with_monitoring().with_registration().build())
if __name__ == "__main__":
    from chapkit.api import run_app
    run_app("main:app", reload=False, port=9090)

