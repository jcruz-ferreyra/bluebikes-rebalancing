# tasks/run_optimization/types.py

from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class ModelParams(BaseModel):
    """Parameters of the multi-vehicle rebalancing MIQP."""

    model_config = ConfigDict(extra="forbid")

    truck_capacity: int = 20  # Q: per-vehicle capacity in bikes
    fleet_size: int = 3  # K: maximum number of vehicles that may be used
    depot_capacity: int = 20  # S: total bikes the fleet can source/return at the depot
    buffer: int = 2  # B: minimum bikes and docks at each station after rebalancing
    alpha: float = 1.0  # distance cost weight ($/meter)
    beta: float = 10.0  # service quality weight ($/bike²)
    gamma: float = 0.0  # fixed cost per deployed vehicle
    service_time: float = 5.0  # fixed time per station stop (minutes)
    time_per_bike: float = 1.0  # variable time per bike loaded/unloaded (minutes)
    max_operation_time: float = 180.0  # T_MAX: per-vehicle operational window (minutes)


class SolverParams(BaseModel):
    """Pyomo solver configuration."""

    model_config = ConfigDict(extra="forbid")

    factory: str = "gurobi"  # "gurobi", "cplex", or "glpk"
    time_limit: int = 300  # solver time limit in seconds
    mip_gap: float = 0.01  # relative MIP optimality gap
    threads: int = 4  # number of solver threads


class PlotParams(BaseModel):
    """Rebalancing map plot configuration."""

    model_config = ConfigDict(extra="forbid")

    save_plot: bool = True  # whether to save the rebalancing map
    zoom: int = 14  # basemap tile zoom level


class RunOptimizationContext(BaseModel):
    """Context for running the multi-vehicle bike rebalancing optimization model."""

    # protected_namespaces=(): model_params describes the optimization model,
    # not a pydantic BaseModel attribute.
    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    target_date: str  # YYYY-MM-DD format
    output_data_dir: Path

    model_params: ModelParams = ModelParams()
    solver_params: SolverParams = SolverParams()
    plot_params: PlotParams = PlotParams()

    output_storage: Literal["local", "drive"] = "local"

    @field_validator("target_date")
    @classmethod
    def _check_target_date(cls, value: str) -> str:
        # Date must be a real calendar date, not just a digit pattern
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            raise ValueError(f"target_date must be in YYYY-MM-DD format, got '{value}'")
        return value

    @model_validator(mode="after")
    def _check_inputs(self) -> "RunOptimizationContext":
        # Required inputs must exist before any loading starts (read-only checks)
        _check_file_exists(self.station_info_path, "processed station_information.csv")
        _check_file_exists(self.dist_ttime_path, "distance/travel time matrix")
        _check_file_exists(self.initial_status_path, f"initial_status for {self.target_date}")
        _check_file_exists(self.demand_path, f"demand forecast for {self.target_date}")
        _check_file_exists(self.routes_shapefile_path, "routes shapefile")
        return self

    @property
    def processed_dir(self) -> Path:
        """Path to processed data directory."""
        return self.output_data_dir / "processed"

    @property
    def station_info_path(self) -> Path:
        """Path to processed station information CSV."""
        return self.processed_dir / "stations" / "station_information.csv"

    @property
    def dist_ttime_path(self) -> Path:
        """Path to distance/travel time CSV."""
        return self.processed_dir / "network" / "dist_ttime_long.csv"

    @property
    def routes_shapefile_path(self) -> Path:
        """Path to routes shapefile."""
        return self.processed_dir / "network" / "routes_long_wgs84" / "routes_long_wgs84.shp"

    @property
    def initial_status_path(self) -> Path:
        """Path to initial status CSV for target date."""
        date_str = self.target_date.replace("-", "")
        return self.processed_dir / "initial_status" / f"initial_status_{date_str}.csv"

    @property
    def demand_path(self) -> Path:
        """Path to demand forecast CSV for target date."""
        date_str = self.target_date.replace("-", "")
        return self.processed_dir / "demand" / f"demand_{date_str}.csv"

    @property
    def results_dir(self) -> Path:
        """Path to multi-vehicle optimization results directory for target date."""
        date_str = self.target_date.replace("-", "")
        path = self.output_data_dir / "rebalancing_results" / "results" / date_str
        path.mkdir(parents=True, exist_ok=True)
        return path


def _check_file_exists(file_path: Path, file_description: str) -> None:
    """Raise when a required input file is missing (read-only validity check)."""
    if not file_path.exists():
        raise ValueError(
            f"Required file not found: {file_path} ({file_description})\n"
            f"Please run prerequisite tasks first."
        )
