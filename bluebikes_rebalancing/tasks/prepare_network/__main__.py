# tasks/prepare_network/__main__.py

from pathlib import Path

from bluebikes_rebalancing.config import LOCAL_DATA_DIR, DRIVE_DATA_DIR
from bluebikes_rebalancing.utils import check_missing_keys, load_config, setup_logging

# Setup logging
script_name = Path(__file__).parent.name
logger = setup_logging(script_name, LOCAL_DATA_DIR)

# Import task components
from bluebikes_rebalancing.tasks.prepare_network import (
    PrepareNetworkContext,
    prepare_network,
)

logger.info("=" * 80)
logger.info("Starting prepare_network task")
logger.info("=" * 80)

# Load config
CONFIG_PATH = Path(__file__).parent.resolve() / "config.yaml"
logger.info(f"Loading config from: {CONFIG_PATH}")
script_config = load_config(CONFIG_PATH)

# Validate config
required_keys = ["depot_lat_lon", "network_bbox"]
check_missing_keys(required_keys, script_config)

# Parse config
DEPOT_LAT_LON = tuple(script_config["depot_lat_lon"])
NETWORK_BBOX = tuple(script_config["network_bbox"])
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

logger.info(f"Depot location: {DEPOT_LAT_LON}")
logger.info(f"Network bounding box: {NETWORK_BBOX}")

# Create context
context = PrepareNetworkContext(
    depot_lat_lon=DEPOT_LAT_LON,
    network_bbox=NETWORK_BBOX,
    output_data_dir=OUTPUT_DATA_DIR,
    output_storage=OUTPUT_STORAGE,
)

# Call main function
prepare_network(context)

logger.info("=" * 80)
logger.info("✓ prepare_network task completed successfully")
logger.info("=" * 80)
