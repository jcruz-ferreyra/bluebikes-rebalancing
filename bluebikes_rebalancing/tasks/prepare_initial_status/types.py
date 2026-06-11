# tasks/prepare_initial_status/types.py

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class PrepareInitialStatusContext(BaseModel):
    """Context for preparing daily initial status files."""

    model_config = ConfigDict(extra="forbid")

    status_start_date: str  # YYYY-MM-DD format
    status_end_date: str  # YYYY-MM-DD format
    output_data_dir: Path

    @field_validator("status_start_date", "status_end_date")
    @classmethod
    def _check_date_format(cls, value: str) -> str:
        # Dates must be real calendar dates, not just digit patterns
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            raise ValueError(f"Date must be in YYYY-MM-DD format, got '{value}'")
        return value

    @model_validator(mode="after")
    def _check_range_and_inputs(self) -> "PrepareInitialStatusContext":
        # End date must not precede start date
        start_date = datetime.strptime(self.status_start_date, "%Y-%m-%d")
        end_date = datetime.strptime(self.status_end_date, "%Y-%m-%d")
        if end_date < start_date:
            raise ValueError(
                f"status_end_date must be after status_start_date, "
                f"got '{self.status_end_date}' < '{self.status_start_date}'"
            )

        # Required inputs must exist before any loading starts (read-only checks)
        _check_file_exists(self.raw_station_info_path, "station_information.csv")
        _check_file_exists(self.stations_of_interest_path, "stations_of_interest.json")
        _check_file_exists(self.processed_station_info_path, "processed station_information.csv")
        if not self.raw_status_dir.is_dir():
            raise ValueError(
                f"Required directory not found: {self.raw_status_dir} (station status directory)"
            )

        return self

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


def _check_file_exists(file_path: Path, file_description: str) -> None:
    """Raise when a required input file is missing (read-only validity check)."""
    if not file_path.exists():
        raise ValueError(f"Required file not found: {file_path} ({file_description})")
