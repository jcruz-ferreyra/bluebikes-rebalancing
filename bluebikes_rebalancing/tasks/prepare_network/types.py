from dataclasses import dataclass
from pathlib import Path


@dataclass
class PrepareNetworkContext:
    """Context for preparing network distance and travel time matrices."""

    depot_lat_lon: tuple[float, float]
    network_bbox: tuple[float, float, float, float]  # (west, south, east, north)
    output_data_dir: Path
    output_storage: str = "local"  # "local" or "drive"

    def __post_init__(self):
        # Validate output directory
        self.output_data_dir.mkdir(parents=True, exist_ok=True)

        # Validate storage option
        _validate_storage(self.output_storage)

        # Validate depot coordinates
        _validate_lat_lon(self.depot_lat_lon)

        # Validate bounding box
        _validate_bbox(self.network_bbox)

        # Validate stations file exists
        _validate_stations_file(self.station_metadata_path)

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


def _validate_lat_lon(lat_lon: tuple[float, float]) -> None:
    """
    Validate latitude/longitude coordinates.

    Args:
        lat_lon: Tuple of (latitude, longitude)

    Raises:
        ValueError: If coordinates are out of valid range
    """
    lat, lon = lat_lon
    if not (-90 <= lat <= 90):
        raise ValueError(f"Latitude must be between -90 and 90, got {lat}")
    if not (-180 <= lon <= 180):
        raise ValueError(f"Longitude must be between -180 and 180, got {lon}")


def _validate_bbox(bbox: tuple[float, float, float, float]) -> None:
    """
    Validate bounding box coordinates.

    Args:
        bbox: Tuple of (west, south, east, north)

    Raises:
        ValueError: If bounding box is invalid
    """
    west, south, east, north = bbox

    if not (-180 <= west <= 180 and -180 <= east <= 180):
        raise ValueError(f"Longitude values must be between -180 and 180")
    if not (-90 <= south <= 90 and -90 <= north <= 90):
        raise ValueError(f"Latitude values must be between -90 and 90")
    if west >= east:
        raise ValueError(f"West ({west}) must be less than East ({east})")
    if south >= north:
        raise ValueError(f"South ({south}) must be less than North ({north})")


def _validate_stations_file(file_path: Path) -> None:
    """
    Validate that station information file exists.

    Args:
        file_path: Path to station_information.csv

    Raises:
        FileNotFoundError: If file does not exist
    """
    if not file_path.exists():
        raise FileNotFoundError(
            f"Station information file not found: {file_path}\n"
            f"Please run download_stations_data task first."
        )
