# tasks/run_optimization/__main__.py
#
# Usage:
#   pixi run python -m bluebikes_rebalancing.tasks.run_optimization                                  # default config date and params
#   pixi run python -m bluebikes_rebalancing.tasks.run_optimization target_date=2026-03-05           # another target date
#   pixi run python -m bluebikes_rebalancing.tasks.run_optimization model_params.beta=100 model_params.fleet_size=2  # tweak the MIQP
#   pixi run python -m bluebikes_rebalancing.tasks.run_optimization -m model_params.gamma=1,10,100,1000  # sweep deployment cost

import logging

from dotenv import load_dotenv
import hydra
from omegaconf import DictConfig, OmegaConf

# LOCAL_DIR must be in the environment before Hydra resolves ${oc.env:...}
load_dotenv()

from bluebikes_rebalancing.tasks.run_optimization import (  # noqa: E402
    RunOptimizationContext,
    run_optimization,
)

logger = logging.getLogger(__name__)


@hydra.main(version_base=None, config_path="conf", config_name="config")
def main(cfg: DictConfig) -> None:
    logger.info("=" * 80)
    logger.info("Starting run_optimization task")
    logger.info("=" * 80)

    script_config = OmegaConf.to_container(cfg, resolve=True)

    # Output roots come from the composed storage group (defaults: storage=local)
    storage = script_config.pop("storage")

    # Create and validate context (the composed config feeds the model directly)
    context = RunOptimizationContext(**script_config, output_data_dir=storage["data_dir"])

    logger.info(f"Using {storage['name']} storage: {context.output_data_dir}")
    logger.info(f"Target date: {context.target_date}")
    logger.info(f"Model parameters: {context.model_params}")
    logger.info(f"Solver parameters: {context.solver_params}")

    run_optimization(context)

    logger.info("=" * 80)
    logger.info("✓ run_optimization task completed successfully")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()
