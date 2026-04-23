# tasks/prepare_demand/prepare_demand.py

import logging
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

from .types import PrepareDemandContext

logger = logging.getLogger(__name__)


# ============================================================================
# Helper functions
# ============================================================================


def _load_station_metadata(ctx: PrepareDemandContext) -> pd.DataFrame:
    """
    Load station metadata for mapping station IDs.

    Args:
        ctx: PrepareDemandContext with configuration

    Returns:
        DataFrame with station metadata
    """
    logger.info("=" * 60)
    logger.info("Loading station metadata")
    logger.info("=" * 60)

    stations_df = pd.read_csv(ctx.station_metadata_path)

    logger.info(f"✓ Loaded metadata for {len(stations_df)} stations")

    return stations_df


def _load_all_forecast(ctx: PrepareDemandContext) -> dict[str, pd.DataFrame]:
    """
    Load all station forecast files.

    Args:
        ctx: PrepareDemandContext with configuration

    Returns:
        Dictionary mapping station_id to forecast DataFrame
    """
    logger.info("=" * 60)
    logger.info(f"Loading demand from model: {ctx.model_name}")
    logger.info("=" * 60)

    if not ctx.demand_dir.exists():
        raise FileNotFoundError(
            f"Forecasts directory not found: {ctx.demand_dir}\n"
            f"Please run forecast_{ctx.model_name} task first."
        )

    # Find all forecast CSV files
    csv_files = list(ctx.demand_dir.glob("*_forecast.csv"))

    if not csv_files:
        raise FileNotFoundError(f"No forecast files found in {ctx.demand_dir}")

    logger.info(f"Found {len(csv_files)} forecast files")

    # Load all demand
    forecast_dict = {}
    for csv_file in csv_files:
        station_id = csv_file.stem.replace("_forecast", "")

        df = pd.read_csv(csv_file)
        df["ds"] = pd.to_datetime(df["ds"])

        forecast_dict[station_id] = df

    logger.info(f"✓ Loaded demand for {len(forecast_dict)} stations")

    return forecast_dict


def _generate_date_range(ctx: PrepareDemandContext) -> list[pd.Timestamp]:
    """
    Generate list of dates for demand file generation.

    Args:
        ctx: PrepareDemandContext with date range

    Returns:
        List of Timestamp objects
    """
    start = pd.to_datetime(ctx.demand_start_date)
    end = pd.to_datetime(ctx.demand_end_date)

    date_range = pd.date_range(start=start, end=end, freq="D")

    logger.info(f"Generating demand files for {len(date_range)} days")
    logger.info(f"  Date range: {start.date()} to {end.date()}")

    return date_range.tolist()


def _prepare_daily_demand(
    target_date: pd.Timestamp, forecast_dict: dict[str, pd.DataFrame], stations_df: pd.DataFrame
) -> pd.DataFrame:
    """
    Prepare demand forecast for a single day across all stations.

    Args:
        target_date: Date to generate demand for
        forecast_dict: Dictionary of station demand
        stations_df: Station metadata DataFrame

    Returns:
        DataFrame with demand for all stations on target_date
    """
    daily_demand = []
    missing_stations = []

    for station_id, forecast_df in forecast_dict.items():
        # Find forecast for target_date
        forecast_row = forecast_df[forecast_df["ds"] == target_date]

        if forecast_row.empty:
            missing_stations.append(station_id)
            continue

        # Extract demand and round to integers, cap negatives to 0
        pickups = max(0, int(round(forecast_row["pickups_forecast"].values[0])))
        dropoffs = max(0, int(round(forecast_row["dropoffs_forecast"].values[0])))

        daily_demand.append(
            {"station_id": station_id, "pickups_forecast": pickups, "dropoffs_forecast": dropoffs}
        )

    if missing_stations:
        logger.warning(
            f"  {len(missing_stations)} stations missing forecast for {target_date.date()}: "
            f"{missing_stations[:5]}{'...' if len(missing_stations) > 5 else ''}"
        )

    if not daily_demand:
        raise ValueError(f"No demand available for {target_date.date()}")

    demand_df = pd.DataFrame(daily_demand)

    # Merge with station metadata to add idx
    demand_df = demand_df.merge(
        stations_df[["short_name", "idx"]], left_on="station_id", right_on="short_name", how="left"
    )

    # Reorder columns: idx, station_id, pickups_forecast, dropoffs_forecast
    demand_df = demand_df[["idx", "station_id", "pickups_forecast", "dropoffs_forecast"]]
    demand_df = demand_df.sort_values("idx").reset_index(drop=True)

    return demand_df


def _save_daily_demand(
    demand_df: pd.DataFrame, target_date: pd.Timestamp, ctx: PrepareDemandContext
) -> None:
    """
    Save daily demand file.

    Args:
        demand_df: DataFrame with demand for all stations
        target_date: Date for this demand file
        ctx: PrepareDemandContext with output paths
    """
    # Format date as YYYYMMDD for filename
    date_str = target_date.strftime("%Y%m%d")
    output_path = ctx.demand_dir / f"demand_{date_str}.csv"

    demand_df.to_csv(output_path, index=False)


# ============================================================================
# Main public function
# ============================================================================


def prepare_demand(ctx: PrepareDemandContext) -> None:
    """
    Prepare daily demand forecast files for optimization model.

    Args:
        ctx: PrepareDemandContext containing configuration and output paths
    """
    logger.info("Starting forecast preparation")
    logger.info(f"Input directory: {ctx.demand_dir}")
    logger.info(f"Output directory: {ctx.demand_dir}")

    # Load station metadata
    stations_df = _load_station_metadata(ctx)

    # Load all demand
    forecast_dict = _load_all_forecast(ctx)

    # Generate date range
    date_range = _generate_date_range(ctx)

    # Generate demand file for each date
    logger.info("=" * 60)
    logger.info("Generating daily demand files")
    logger.info("=" * 60)

    for target_date in date_range:
        demand_df = _prepare_daily_demand(target_date, forecast_dict, stations_df)
        _save_daily_demand(demand_df, target_date, ctx)

    logger.info("=" * 60)
    logger.info("✓ Forecast preparation completed")
    logger.info(f"  Generated {len(date_range)} demand files")
