# tasks/prepare_initial_status/types.py

from dataclasses import dataclass
from pathlib import Path
from datetime import datetime


@dataclass
class PrepareInitialStatusContext:
    """Context for preparing daily initial status files."""

    status_start_date: str  # YYYY-MM-DD format
    status_end_date: str  # YYYY-MM-DD format
    output_data_dir: Path
    output_storage: str = "local"  # "local" or "drive"

    def __post_init__(self):
        # Validate output directory
        self.output_data_dir.mkdir(parents=True, exist_ok=True)

        # Validate storage option
        _validate_storage(self.output_storage)

        # Validate status dates
        _validate_status_date(self.status_start_date)
        _validate_status_date(self.status_end_date)
        _validate_date_range(self.status_start_date, self.status_end_date)

        # Validate required input files exist
        _validate_file_exists(self.raw_station_info_path, "station_information.csv")
        _validate_file_exists(self.stations_of_interest_path, "stations_of_interest.json")
        _validate_file_exists(
            self.processed_station_info_path, "processed station_information.csv"
        )
        _validate_directory_exists(self.raw_status_dir, "station status directory")

    @property
    def raw_stations_dir(self) -> Path:
        """Path to raw station metadata."""
        return self.output_data_dir / "raw" / "stations"

    @property
    def raw_status_dir(self) -> Path:
        """Path to raw station status snapshots."""
        return self.raw_stations_dir / "status"

    @property
    def raw_station_info_path(self) -> Path:
        """Path to raw station information CSV (with station_id mapping)."""
        return self.raw_stations_dir / "station_information.csv"

    @property
    def stations_of_interest_path(self) -> Path:
        """Path to stations of interest JSON file."""
        return self.raw_stations_dir / "stations_of_interest.json"

    @property
    def processed_station_info_path(self) -> Path:
        """Path to processed station information CSV (with idx)."""
        return self.output_data_dir / "processed" / "stations" / "station_information.csv"

    @property
    def initial_status_dir(self) -> Path:
        """Path to initial status outputs."""
        path = self.output_data_dir / "processed" / "initial_status"
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


def _validate_status_date(date_str: str) -> None:
    """
    Validate status date format.

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
            f"status_end_date must be after status_start_date, "
            f"got '{end_date_str}' < '{start_date_str}'"
        )


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
        raise FileNotFoundError(f"Required file not found: {file_path} ({file_description})")


def _validate_directory_exists(dir_path: Path, dir_description: str) -> None:
    """
    Validate that a required directory exists.

    Args:
        dir_path: Path to directory
        dir_description: Description for error message

    Raises:
        FileNotFoundError: If directory does not exist
    """
    if not dir_path.exists() or not dir_path.is_dir():
        raise FileNotFoundError(f"Required directory not found: {dir_path} ({dir_description})")
