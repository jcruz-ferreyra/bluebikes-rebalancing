# tasks/prepare_demand/types.py

from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class PrepareDemandContext(BaseModel):
    """Context for preparing daily demand forecast files."""

    # protected_namespaces=(): model_name is forecasting-model vocabulary here,
    # not a pydantic BaseModel attribute.
    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    model_name: str
    demand_start_date: str  # YYYY-MM-DD format
    demand_end_date: str  # YYYY-MM-DD format
    output_data_dir: Path
    output_storage: Literal["local", "drive"] = "local"

    @field_validator("demand_start_date", "demand_end_date")
    @classmethod
    def _check_date_format(cls, value: str) -> str:
        # Dates must be real calendar dates, not just digit patterns
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            raise ValueError(f"Date must be in YYYY-MM-DD format, got '{value}'")
        return value

    @model_validator(mode="after")
    def _check_range_and_inputs(self) -> "PrepareDemandContext":
        # End date must not precede start date
        start_date = datetime.strptime(self.demand_start_date, "%Y-%m-%d")
        end_date = datetime.strptime(self.demand_end_date, "%Y-%m-%d")
        if end_date < start_date:
            raise ValueError(
                f"demand_end_date must be after demand_start_date, "
                f"got '{self.demand_end_date}' < '{self.demand_start_date}'"
            )

        # Station metadata must exist before any loading starts
        if not self.station_metadata_path.exists():
            raise ValueError(
                f"Station metadata file not found: {self.station_metadata_path}\n"
                f"Please run the prepare_network task to generate station_information.csv"
            )

        return self

    @property
    def forecasts_dir(self) -> Path:
        """Path to forecast inputs (from model)."""
        return self.output_data_dir / "timeseries_results" / "forecasts" / self.model_name

    @property
    def demand_dir(self) -> Path:
        """Path to daily demand outputs."""
        path = self.output_data_dir / "processed" / "demand"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def station_metadata_path(self) -> Path:
        """Path to station information CSV."""
        return self.output_data_dir / "processed" / "stations" / "station_information.csv"
