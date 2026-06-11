# bluebikes_rebalancing/config.py

import os
from pathlib import Path

from dotenv import load_dotenv

# Bootstrap: put .env values into the process environment. Hydra's oc.env
# resolver reads the environment, and the notebooks read the constants below.
load_dotenv()

# Notebook-side path resolution. The tasks do NOT use this: their data/model
# roots come from the hydra storage config group (bluebikes_rebalancing/conf).
if os.getenv("CI"):  # GitHub Actions sets CI=true
    LOCAL_DIR = Path(".").resolve()
else:
    LOCAL_DIR = Path(os.getenv("LOCAL_DIR")).resolve()
    if not LOCAL_DIR.exists():
        raise ValueError(f"LOCAL_DIR path '{LOCAL_DIR}' from .env does not exist.")

DATA_DIR = LOCAL_DIR / Path(os.getenv("DATA_FOLDER", "data"))
MODELS_DIR = LOCAL_DIR / Path(os.getenv("MODELS_FOLDER", "models"))

# Secrets stay here on purpose: the composed hydra config is snapshotted into
# every run dir (.hydra/config.yaml), so API keys must never be interpolated
# into it. Code reads them from this module instead.
GUROBI_APIKEY = os.getenv("GUROBI_APIKEY")
