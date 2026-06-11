# tasks/prepare_network/__main__.py
#
# Usage:
#   pixi run python -m bluebikes_rebalancing.tasks.prepare_network                                          # default depot and bbox
#   pixi run python -m bluebikes_rebalancing.tasks.prepare_network 'depot_lat_lon=[42.34,-71.10]'           # alternative depot
#   pixi run python -m bluebikes_rebalancing.tasks.prepare_network 'network_bbox=[-71.12,42.32,-71.07,42.36]'  # wider bbox

import logging

from dotenv import load_dotenv
import hydra
from omegaconf import DictConfig, OmegaConf

# LOCAL_DIR must be in the environment before Hydra resolves ${oc.env:...}
load_dotenv()

from bluebikes_rebalancing.tasks.prepare_network import (  # noqa: E402
    PrepareNetworkContext,
    prepare_network,
)

logger = logging.getLogger(__name__)


@hydra.main(version_base=None, config_path="conf", config_name="config")
def main(cfg: DictConfig) -> None:
    logger.info("=" * 80)
    logger.info("Starting prepare_network task")
    logger.info("=" * 80)

    script_config = OmegaConf.to_container(cfg, resolve=True)

    # Output roots come from the composed storage group (defaults: storage=local)
    storage = script_config.pop("storage")

    # Create and validate context (the composed config feeds the model directly)
    context = PrepareNetworkContext(**script_config, output_data_dir=storage["data_dir"])

    logger.info(f"Using {storage['name']} storage: {context.output_data_dir}")
    logger.info(f"Depot location: {context.depot_lat_lon}")
    logger.info(f"Network bounding box: {context.network_bbox}")

    prepare_network(context)

    logger.info("=" * 80)
    logger.info("✓ prepare_network task completed successfully")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()
