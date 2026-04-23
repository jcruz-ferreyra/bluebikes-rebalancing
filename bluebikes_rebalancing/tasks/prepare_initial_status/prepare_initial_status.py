# tasks/prepare_initial_status/prepare_initial_status.py

import json
import logging
from datetime import datetime
from pathlib import Path

import pandas as pd

from .types import PrepareInitialStatusContext

logger = logging.getLogger(__name__)


# ============================================================================
# Helper functions
# ============================================================================


def _load_station_mappings(ctx: PrepareInitialStatusContext) -> pd.DataFrame:
    """
    Load and merge station mapping files.

    Args:
        ctx: PrepareInitialStatusContext with configuration

    Returns:
        DataFrame with columns: station_id, short_name, idx
    """
    logger.info("=" * 60)
    logger.info("Loading station mappings")
    logger.info("=" * 60)

    # Load stations of interest
    with open(ctx.stations_of_interest_path) as f:
        stations_of_interest = json.load(f)
    logger.info(f"✓ Loaded {len(stations_of_interest)} stations of interest")

    # Load raw station information (has station_id → short_name mapping)
    raw_station_info = pd.read_csv(ctx.raw_station_info_path)
    logger.info(f"✓ Loaded raw station info: {len(raw_station_info)} stations")

    # Filter to stations of interest
    filt = raw_station_info["short_name"].isin(stations_of_interest)
    raw_station_info = raw_station_info.loc[filt, ["station_id", "short_name"]].copy()

    # Load processed station information (has idx mapping)
    processed_station_info = pd.read_csv(ctx.processed_station_info_path)
    logger.info(f"✓ Loaded processed station info: {len(processed_station_info)} stations")

    # Merge on short_name
    station_mapping = raw_station_info.merge(
        processed_station_info[["short_name", "idx"]],
        on="short_name",
        how="left",
    )

    # Check for failed merges
    n_missing = station_mapping["idx"].isna().sum()
    if n_missing > 0:
        missing_stations = station_mapping.loc[
            station_mapping["idx"].isna(), "short_name"
        ].tolist()
        logger.warning(
            f"⚠ {n_missing} stations from stations_of_interest not found in processed station info: {missing_stations}"
        )
        # Drop stations without idx mapping
        station_mapping = station_mapping.dropna(subset=["idx"]).reset_index(drop=True)

    # Convert idx to int
    station_mapping["idx"] = station_mapping["idx"].astype(int)

    # Select final columns
    station_mapping = station_mapping[["station_id", "short_name", "idx"]]

    logger.info(f"✓ Created mapping for {len(station_mapping)} stations")

    return station_mapping


def _parse_status_filename(filename: str) -> tuple[str, str]:
    """
    Parse status filename to extract date and time.

    Args:
        filename: Filename like 'station_status_260216_054810.csv'

    Returns:
        Tuple of (date_str in YYYY-MM-DD, time_str in HHMMSS)
    """
    # Remove extension and split
    name = filename.replace(".csv", "")
    parts = name.split("_")

    # Extract date and time parts (YYMMDD_HHMMSS)
    date_part = parts[2]  # YYMMDD
    time_part = parts[3]  # HHMMSS

    # Convert YYMMDD to YYYY-MM-DD
    year = "20" + date_part[:2]
    month = date_part[2:4]
    day = date_part[4:6]
    date_str = f"{year}-{month}-{day}"

    return date_str, time_part


def _find_earliest_status_files(
    ctx: PrepareInitialStatusContext, date_range: list[pd.Timestamp]
) -> dict[str, Path]:
    """
    Find the earliest status file for each date in the range.

    Args:
        ctx: PrepareInitialStatusContext with paths
        date_range: List of dates to find status files for

    Returns:
        Dictionary mapping date string (YYYY-MM-DD) to file path
    """
    logger.info("=" * 60)
    logger.info("Finding earliest status files for each date")
    logger.info("=" * 60)

    # List all status CSV files
    status_files = list(ctx.raw_status_dir.glob("station_status_*.csv"))

    if not status_files:
        raise FileNotFoundError(f"No status files found in {ctx.raw_status_dir}")

    logger.info(f"Found {len(status_files)} total status files")

    # Parse all filenames and group by date
    file_dict = {}
    for file_path in status_files:
        try:
            date_str, time_str = _parse_status_filename(file_path.name)

            if date_str not in file_dict:
                file_dict[date_str] = []

            file_dict[date_str].append((time_str, file_path))
        except Exception as e:
            logger.warning(f"Could not parse filename {file_path.name}: {e}")
            continue

    # For each date in range, find earliest file
    earliest_files = {}
    missing_dates = []

    for target_date in date_range:
        date_str = target_date.strftime("%Y-%m-%d")

        if date_str not in file_dict:
            missing_dates.append(date_str)
            continue

        # Sort by time and take earliest
        files_for_date = sorted(file_dict[date_str], key=lambda x: x[0])
        earliest_time, earliest_file = files_for_date[0]

        earliest_files[date_str] = earliest_file
        logger.info(f"  {date_str}: {earliest_file.name} (time: {earliest_time})")

    if missing_dates:
        logger.warning(
            f"⚠ No status files found for {len(missing_dates)} dates: {missing_dates[:5]}{'...' if len(missing_dates) > 5 else ''}"
        )

    logger.info(f"✓ Found earliest files for {len(earliest_files)} dates")

    return earliest_files


def _generate_date_range(ctx: PrepareInitialStatusContext) -> list[pd.Timestamp]:
    """
    Generate list of dates for status file generation.

    Args:
        ctx: PrepareInitialStatusContext with date range

    Returns:
        List of Timestamp objects
    """
    start = pd.to_datetime(ctx.status_start_date)
    end = pd.to_datetime(ctx.status_end_date)

    date_range = pd.date_range(start=start, end=end, freq="D")

    logger.info(f"Generating status files for {len(date_range)} days")
    logger.info(f"  Date range: {start.date()} to {end.date()}")

    return date_range.tolist()


def _prepare_daily_status(
    status_file: Path,
    station_mapping: pd.DataFrame,
) -> pd.DataFrame:
    """
    Prepare initial status for a single day.

    Args:
        status_file: Path to status CSV file
        station_mapping: DataFrame with station_id, short_name, idx

    Returns:
        DataFrame with columns: idx, short_name, initial_status
    """
    # Load status file
    status_df = pd.read_csv(status_file)

    # Filter to installed and operational stations
    filt = (status_df["is_installed"] == 1) & (status_df["is_renting"] == 1)
    status_df = status_df.loc[filt, :].copy()

    # Merge with station mapping on station_id
    status_df = status_df.merge(station_mapping, on="station_id", how="inner")

    # Calculate initial status (total bikes available)
    status_df["initial_status"] = status_df["num_bikes_available"]

    # Select and order columns
    result_df = status_df[["idx", "short_name", "initial_status"]].copy()
    result_df = result_df.sort_values("idx").reset_index(drop=True)

    return result_df


def _save_daily_status(
    status_df: pd.DataFrame, target_date: pd.Timestamp, ctx: PrepareInitialStatusContext
) -> None:
    """
    Save daily initial status file.

    Args:
        status_df: DataFrame with initial status for all stations
        target_date: Date for this status file
        ctx: PrepareInitialStatusContext with output paths
    """
    # Format date as YYYYMMDD for filename
    date_str = target_date.strftime("%Y%m%d")
    output_path = ctx.initial_status_dir / f"initial_status_{date_str}.csv"

    status_df.to_csv(output_path, index=False)


# ============================================================================
# Main public function
# ============================================================================


def prepare_initial_status(ctx: PrepareInitialStatusContext) -> None:
    """
    Prepare daily initial status files for optimization model.

    Args:
        ctx: PrepareInitialStatusContext containing configuration and output paths
    """
    logger.info("Starting initial status preparation")
    logger.info(f"Input directory: {ctx.raw_status_dir}")
    logger.info(f"Output directory: {ctx.initial_status_dir}")

    # Load station mappings
    station_mapping = _load_station_mappings(ctx)

    # Generate date range
    date_range = _generate_date_range(ctx)

    # Find earliest status file for each date
    earliest_files = _find_earliest_status_files(ctx, date_range)

    # Generate status file for each date
    logger.info("=" * 60)
    logger.info("Generating daily initial status files")
    logger.info("=" * 60)

    files_generated = 0
    for target_date in date_range:
        date_str = target_date.strftime("%Y-%m-%d")

        if date_str not in earliest_files:
            logger.warning(f"  Skipping {date_str}: no status file available")
            continue

        status_file = earliest_files[date_str]
        status_df = _prepare_daily_status(status_file, station_mapping)
        _save_daily_status(status_df, target_date, ctx)
        files_generated += 1

    logger.info("=" * 60)
    logger.info("✓ Initial status preparation completed")
    logger.info(f"  Generated {files_generated} status files")
