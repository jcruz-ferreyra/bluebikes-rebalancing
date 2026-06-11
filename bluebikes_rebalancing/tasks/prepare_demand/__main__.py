# tasks/prepare_demand/__main__.py
#
# Usage:
#   pixi run python -m bluebikes_rebalancing.tasks.prepare_demand                                                        # default config range
#   pixi run python -m bluebikes_rebalancing.tasks.prepare_demand demand_start_date=2026-05-01 demand_end_date=2026-05-31  # override the range
#   pixi run python -m bluebikes_rebalancing.tasks.prepare_demand model_name=sarima                                      # another forecast source

import logging

from dotenv import load_dotenv
import hydra
from omegaconf import DictConfig, OmegaConf

# LOCAL_DIR must be in the environment before Hydra resolves ${oc.env:...}
load_dotenv()

from bluebikes_rebalancing.config import LOCAL_DATA_DIR, DRIVE_DATA_DIR  # noqa: E402
from bluebikes_rebalancing.tasks.prepare_demand import (  # noqa: E402
    PrepareDemandContext,
    prepare_demand,
)

logger = logging.getLogger(__name__)


@hydra.main(version_base=None, config_path="conf", config_name="config")
def main(cfg: DictConfig) -> None:
    logger.info("=" * 80)
    logger.info("Starting prepare_demand task")
    logger.info("=" * 80)

    script_config = OmegaConf.to_container(cfg, resolve=True)

    # Resolve the storage-dependent output directory; output_storage itself is
    # validated by the context model, not here
    output_storage = script_config.get("output_storage", "local")
    if output_storage == "drive":
        if DRIVE_DATA_DIR is None:
            raise ValueError(
                "DRIVE_DATA_DIR not configured. Check .env file or use 'local' storage."
            )
        output_data_dir = DRIVE_DATA_DIR
    else:
        output_data_dir = LOCAL_DATA_DIR

    # Create and validate context (the composed config feeds the model directly)
    context = PrepareDemandContext(**script_config, output_data_dir=output_data_dir)

    logger.info(f"Using {context.output_storage} storage: {context.output_data_dir}")
    logger.info(f"Model: {context.model_name}")
    logger.info(f"Demand date range: {context.demand_start_date} to {context.demand_end_date}")

    prepare_demand(context)

    logger.info("=" * 80)
    logger.info("✓ prepare_demand task completed successfully")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()
