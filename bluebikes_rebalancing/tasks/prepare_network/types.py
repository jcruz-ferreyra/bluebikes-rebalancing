# tasks/prepare_network/types.py

from pathlib import Path

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class PrepareNetworkContext(BaseModel):
    """Context for preparing network distance and travel time matrices."""

    model_config = ConfigDict(extra="forbid")

    depot_lat_lon: tuple[float, float]
    network_bbox: tuple[float, float, float, float]  # (west, south, east, north)
    output_data_dir: Path

    @field_validator("depot_lat_lon")
    @classmethod
    def _check_lat_lon(cls, value: tuple[float, float]) -> tuple[float, float]:
        lat, lon = value
        if not (-90 <= lat <= 90):
            raise ValueError(f"Latitude must be between -90 and 90, got {lat}")
        if not (-180 <= lon <= 180):
            raise ValueError(f"Longitude must be between -180 and 180, got {lon}")
        return value

    @field_validator("network_bbox")
    @classmethod
    def _check_bbox(
        cls, value: tuple[float, float, float, float]
    ) -> tuple[float, float, float, float]:
        west, south, east, north = value

        if not (-180 <= west <= 180 and -180 <= east <= 180):
            raise ValueError("Longitude values must be between -180 and 180")
        if not (-90 <= south <= 90 and -90 <= north <= 90):
            raise ValueError("Latitude values must be between -90 and 90")
        if west >= east:
            raise ValueError(f"West ({west}) must be less than East ({east})")
        if south >= north:
            raise ValueError(f"South ({south}) must be less than North ({north})")
        return value

    @model_validator(mode="after")
    def _check_inputs(self) -> "PrepareNetworkContext":
        # Station metadata must exist before any network download starts
        if not self.station_metadata_path.exists():
            raise ValueError(
                f"Station information file not found: {self.station_metadata_path}\n"
                f"Please run download_stations_data task first."
            )
        return self

    @property
    def raw_stations_dir(self) -> Path:
        """Path to raw station metadata."""
        return self.output_data_dir / "raw" / "stations"

    @property
    def station_metadata_path(self) -> Path:
        """Path to station information CSV."""
        return self.raw_stations_dir / "station_information.csv"

    @property
    def processed_stations_dir(self) -> Path:
        """Path to processed stations output."""
        path = self.output_data_dir / "processed" / "stations"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def station_info_path(self) -> Path:
        """Path to station information CSV with indices."""
        return self.processed_stations_dir / "station_information.csv"

    @property
    def processed_network_dir(self) -> Path:
        """Path to processed network output."""
        path = self.output_data_dir / "processed" / "network"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def dist_ttime_path(self) -> Path:
        """Path to distance/travel time CSV in long format."""
        return self.processed_network_dir / "dist_ttime_long.csv"

    @property
    def routes_shapefile_dir(self) -> Path:
        """Path to routes shapefile directory."""
        path = self.processed_network_dir / "routes_long_wgs84"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def routes_shapefile_path(self) -> Path:
        """Path to routes shapefile (WGS84)."""
        return self.routes_shapefile_dir / "routes_long_wgs84.shp"

    @property
    def routes_json_path(self) -> Path:
        """Path to routes JSON with OSM node sequences."""
        return self.processed_network_dir / "routes_node_sequences.json"
