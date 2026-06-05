# tasks/run_optimization_single/__main__.py

from pathlib import Path

from bluebikes_rebalancing.config import LOCAL_DATA_DIR, DRIVE_DATA_DIR
from bluebikes_rebalancing.utils import check_missing_keys, load_config, setup_logging

# Setup logging
script_name = Path(__file__).parent.name
logger = setup_logging(script_name, LOCAL_DATA_DIR)

# Import task components
from bluebikes_rebalancing.tasks.run_optimization_single import (
    RunOptimizationContext,
    run_optimization,
)

logger.info("=" * 80)
logger.info("Starting run_optimization_single task")
logger.info("=" * 80)

# Load config
CONFIG_PATH = Path(__file__).parent.resolve() / "config.yaml"
logger.info(f"Loading config from: {CONFIG_PATH}")
script_config = load_config(CONFIG_PATH)

# Validate config
required_keys = ["target_date"]
check_missing_keys(required_keys, script_config)

# Parse config
TARGET_DATE = script_config["target_date"]
MODEL_PARAMS = script_config.get("model_params", {})
SOLVER_PARAMS = script_config.get("solver_params", {})
PLOT_PARAMS = script_config.get("plot_params", {})
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

logger.info(f"Target date: {TARGET_DATE}")
logger.info(f"Model parameters: {MODEL_PARAMS if MODEL_PARAMS else 'using defaults'}")
logger.info(f"Solver parameters: {SOLVER_PARAMS if SOLVER_PARAMS else 'using defaults'}")

# Create context
context = RunOptimizationContext(
    model_params=MODEL_PARAMS,
    solver_params=SOLVER_PARAMS,
    plot_params=PLOT_PARAMS,
    target_date=TARGET_DATE,
    output_data_dir=OUTPUT_DATA_DIR,
    output_storage=OUTPUT_STORAGE,
)

# Call main function
run_optimization(context)

logger.info("=" * 80)
logger.info("✓ run_optimization_single task completed successfully")
logger.info("=" * 80)
