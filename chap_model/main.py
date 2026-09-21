"""Chapkit service for the lagged heatwave covariate model."""
import os
from pathlib import Path
from chapkit import BaseConfig
from chapkit.api import AssessedStatus, MLServiceBuilder, MLServiceInfo, ModelMetadata, PeriodType
from chapkit.artifact import ArtifactHierarchy
from chapkit.ml import ShellModelRunner
from pydantic import Field

HEAT_COVARIATES = ["heatwave_days", "mean_heat_index", "max_heat_index", "heatwave_event_count"]

class HeatwaveModelConfig(BaseConfig):
    prediction_periods: int = 4
    heat_lag_weeks: int = Field(default=4, ge=1)
    n_samples: int = Field(default=100, ge=1)
    random_seed: int = 42
    n_estimators: int = Field(default=200, ge=1)
    additional_continuous_covariates: list[str] = Field(default_factory=lambda: HEAT_COVARIATES.copy())

runner: ShellModelRunner[HeatwaveModelConfig] = ShellModelRunner(
    train_command="python scripts/train_model.py --data {data_file}",
    predict_command="python scripts/predict_model.py --historic {historic_file} --future {future_file} --output {output_file}",
)
info = MLServiceInfo(
    id="heatwave-covariate-model", display_name="Heatwave covariate model", version="0.1.0",
    description=("Experimental weekly disease model using rainfall, mean temperature, and four-week-lagged "
                 "heatwave covariates. Heat index inputs are measured in degrees Fahrenheit."),
    model_metadata=ModelMetadata(author="gichangi", author_assessed_status=AssessedStatus.red),
    period_type=PeriodType.weekly, allow_free_additional_continuous_covariates=True,
    required_covariates=["rainfall", "mean_temperature"], min_prediction_periods=1, max_prediction_periods=4,
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

