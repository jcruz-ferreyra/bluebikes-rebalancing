# tasks/prepare_demand/__main__.py

from pathlib import Path

from bluebikes_rebalancing.config import LOCAL_DATA_DIR, DRIVE_DATA_DIR
from bluebikes_rebalancing.utils import check_missing_keys, load_config, setup_logging

# Setup logging
script_name = Path(__file__).parent.name
logger = setup_logging(script_name, LOCAL_DATA_DIR)

# Import task components
from bluebikes_rebalancing.tasks.prepare_demand import (
    PrepareDemandContext,
    prepare_demand,
)

logger.info("=" * 80)
logger.info("Starting prepare_demand task")
logger.info("=" * 80)

# Load config
CONFIG_PATH = Path(__file__).parent.resolve() / "config.yaml"
logger.info(f"Loading config from: {CONFIG_PATH}")
script_config = load_config(CONFIG_PATH)

# Validate config
required_keys = ["model_name", "demand_start_date", "demand_end_date"]
check_missing_keys(required_keys, script_config)

# Parse config
MODEL_NAME = script_config["model_name"]
DEMAND_START_DATE = script_config["demand_start_date"]
DEMAND_END_DATE = script_config["demand_end_date"]
OUTPUT_STORAGE = script_config.get("output_storage", "local")

# Determine output directory
if OUTPUT_STORAGE == "drive":
    if DRIVE_DATA_DIR is None:
        raise ValueError("DRIVE_DATA_DIR not configured. Check .env file or use 'local' storage.")
    OUTPUT_DATA_DIR = DRIVE_DATA_DIR
    logger.info(f"Using Drive storage: {OUTPUT_DATA_DIR}")
elif OUTPUT_STORAGE == "local":
    OUTPUT_DATA_DIR = LOCAL_DATA_DIR
    logger.info(f"Using local storage: {OUTPUT_DATA_DIR}")
else:
    raise ValueError(f"Invalid output_storage: '{OUTPUT_STORAGE}'. Use 'local' or 'drive'.")

logger.info(f"Model: {MODEL_NAME}")
logger.info(f"Demand date range: {DEMAND_START_DATE} to {DEMAND_END_DATE}")

# Create context
context = PrepareDemandContext(
    model_name=MODEL_NAME,
    demand_start_date=DEMAND_START_DATE,
    demand_end_date=DEMAND_END_DATE,
    output_data_dir=OUTPUT_DATA_DIR,
    output_storage=OUTPUT_STORAGE,
)

# Call main function
prepare_demand(context)

logger.info("=" * 80)
logger.info("✓ prepare_demand task completed successfully")
logger.info("=" * 80)
