# tasks/prepare_network/__main__.py

from pathlib import Path

from bluebikes_rebalancing.config import LOCAL_DATA_DIR, DRIVE_DATA_DIR
from bluebikes_rebalancing.utils import load_config, setup_logging

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

# Resolve the storage-dependent output directory; output_storage itself is
# validated by the context model, not here
output_storage = script_config.get("output_storage", "local")
if output_storage == "drive":
    if DRIVE_DATA_DIR is None:
        raise ValueError("DRIVE_DATA_DIR not configured. Check .env file or use 'local' storage.")
    output_data_dir = DRIVE_DATA_DIR
else:
    output_data_dir = LOCAL_DATA_DIR

# Create and validate context (the YAML dict feeds the model directly)
context = PrepareNetworkContext(**script_config, output_data_dir=output_data_dir)

logger.info(f"Using {context.output_storage} storage: {context.output_data_dir}")
logger.info(f"Depot location: {context.depot_lat_lon}")
logger.info(f"Network bounding box: {context.network_bbox}")

# Call main function
prepare_network(context)

logger.info("=" * 80)
logger.info("✓ prepare_network task completed successfully")
logger.info("=" * 80)
