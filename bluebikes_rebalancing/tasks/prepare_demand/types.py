# tasks/prepare_forecasts/types.py

from dataclasses import dataclass
from pathlib import Path
from datetime import datetime


@dataclass
class PrepareDemandContext:
    """Context for preparing daily demand forecast files."""

    model_name: str
    demand_start_date: str  # YYYY-MM-DD format
    demand_end_date: str  # YYYY-MM-DD format
    output_data_dir: Path
    output_storage: str = "local"  # "local" or "drive"


    def __post_init__(self):
        # Validate output directory
        self.output_data_dir.mkdir(parents=True, exist_ok=True)

        # Validate storage option
        _validate_storage(self.output_storage)

        # Validate demand dates
        _validate_demand_date(self.demand_start_date)
        _validate_demand_date(self.demand_end_date)
        _validate_date_range(self.demand_start_date, self.demand_end_date)

        # Validate station metadata exists
        if not self.station_metadata_path.exists():
            raise FileNotFoundError(
                f"Station metadata file not found: {self.station_metadata_path}\n"
                f"Please run the prepare_network task to generate station_information.csv"
            )

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


def _validate_demand_date(date_str: str) -> None:
    """
    Validate demand date format.

    Args:
        date_str: Date string in YYYY-MM-DD format

    Raises:
        ValueError: If date format is invalid
    """
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        raise ValueError(f"Date must be in YYYY-MM-DD format, got '{date_str}'")


def _validate_date_range(start_date_str: str, end_date_str: str) -> None:
    """
    Validate that end date is after start date.

    Args:
        start_date_str: Start date string in YYYY-MM-DD format
        end_date_str: End date string in YYYY-MM-DD format

    Raises:
        ValueError: If end date is not after start date
    """
    start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
    end_date = datetime.strptime(end_date_str, "%Y-%m-%d")

    if end_date < start_date:
        raise ValueError(
            f"demand_end_date must be after demand_start_date, "
            f"got '{end_date_str}' < '{start_date_str}'"
        )
