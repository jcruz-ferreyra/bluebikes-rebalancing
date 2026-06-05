# tasks/run_optimization/types.py

from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime
from typing import Dict, Union


@dataclass
class RunOptimizationContext:
    """Context for running the multi-vehicle bike rebalancing optimization model."""

    target_date: str  # YYYY-MM-DD format
    output_data_dir: Path

    model_params: Dict[str, Union[int, float]] = field(default_factory=dict)
    solver_params: Dict[str, Union[str, int, float]] = field(default_factory=dict)
    plot_params: Dict[str, Union[bool, int]] = field(default_factory=dict)

    output_storage: str = "local"  # "local" or "drive"

    def __post_init__(self):
        # Validate output directory
        self.output_data_dir.mkdir(parents=True, exist_ok=True)

        # Validate storage option
        _validate_storage(self.output_storage)

        # Validate target date
        _validate_target_date(self.target_date)

        # Fill model params with defaults
        self.model_params = _fill_model_params_with_defaults(self.model_params)

        # Fill solver params with defaults
        self.solver_params = _fill_solver_params_with_defaults(self.solver_params)

        # Fill plot params with defaults
        self.plot_params = _fill_plot_params_with_defaults(self.plot_params)

        # Validate required input files exist
        _validate_file_exists(self.station_info_path, "processed station_information.csv")
        _validate_file_exists(self.dist_ttime_path, "distance/travel time matrix")
        _validate_file_exists(self.initial_status_path, f"initial_status for {self.target_date}")
        _validate_file_exists(self.demand_path, f"demand forecast for {self.target_date}")
        _validate_file_exists(self.routes_shapefile_path, "routes shapefile")

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
        """Path to multi-vehicle optimization results directory for target date.

        Kept separate from the single-vehicle task's ``results`` directory so the
        two formulations can be run and compared without clobbering each other.
        """
        date_str = self.target_date.replace("-", "")
        path = self.output_data_dir / "rebalancing_results" / "results_multi" / date_str
        path.mkdir(parents=True, exist_ok=True)
        return path


def _validate_storage(storage: str) -> None:
    """
    Validate that the storage option is supported.

    Args:
        storage: Storage option ("local" or "drive")

    Raises:
        ValueError: If storage option is not valid
    """
    valid_storages = ["local", "drive"]
    if storage not in valid_storages:
        raise ValueError(f"output_storage must be one of {valid_storages}, got '{storage}'")


def _validate_target_date(date_str: str) -> None:
    """
    Validate target date format.

    Args:
        date_str: Date string in YYYY-MM-DD format

    Raises:
        ValueError: If date format is invalid
    """
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        raise ValueError(f"target_date must be in YYYY-MM-DD format, got '{date_str}'")


def _validate_file_exists(file_path: Path, file_description: str) -> None:
    """
    Validate that a required file exists.

    Args:
        file_path: Path to file
        file_description: Description for error message

    Raises:
        FileNotFoundError: If file does not exist
    """
    if not file_path.exists():
        raise FileNotFoundError(
            f"Required file not found: {file_path} ({file_description})\n"
            f"Please run prerequisite tasks first."
        )


def _fill_model_params_with_defaults(model_params: Dict) -> Dict:
    """
    Fill missing model parameters with default values.

    Args:
        model_params: User-provided model parameters

    Returns:
        Complete model parameters dictionary
    """
    defaults = {
        "truck_capacity": 20,
        "fleet_size": 3,
        "depot_capacity": 20,
        "buffer": 2,
        "alpha": 1.0,
        "beta": 10.0,
        "gamma": 0.0,
        "service_time": 5.0,
        "time_per_bike": 1.0,
        "max_operation_time": 180.0,
    }

    return {**defaults, **model_params}


def _fill_solver_params_with_defaults(solver_params: Dict) -> Dict:
    """
    Fill missing solver parameters with default values.

    Args:
        solver_params: User-provided solver parameters

    Returns:
        Complete solver parameters dictionary
    """
    defaults = {
        "factory": "gurobi",
        "time_limit": 300,
        "mip_gap": 0.01,
        "threads": 4,
    }

    return {**defaults, **solver_params}


def _fill_plot_params_with_defaults(plot_params: Dict) -> Dict:
    """
    Fill missing plot parameters with default values.

    Args:
        plot_params: User-provided plot parameters

    Returns:
        Complete plot parameters dictionary
    """
    defaults = {
        "save_plot": True,
        "zoom": 14,
    }

    return {**defaults, **plot_params}
