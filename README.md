# BlueBikes Rebalancing

Multi-vehicle bike-rebalancing optimizer for Boston BlueBikes stations: a Pyomo MIQP fed by demand forecasts and solved with Gurobi.

> **Part of a two-part BlueBikes study** — a companion [forecasting project](https://github.com/jcruz-ferreyra/bluebikes_forecasting) covers data engineering and demand forecasting; this repo consumes its forecasts to plan overnight rebalancing routes.

<br>

## Overview

A pipeline that turns per-station demand forecasts and live station status into optimal overnight rebalancing plans. It builds a road-network travel-time matrix between stations, prepares daily demand and initial-status inputs, and solves a multi-vehicle pickup-and-delivery MIQP (capacitated trucks, depot sourcing, service-time budget) that trades off route distance, service quality, and fleet size. It is organized as four independent, runnable tasks plus analysis notebooks. Every task is invoked the same way: `pixi run python -m bluebikes_rebalancing.tasks.<task>`.

### Capabilities

- **Road-network preparation**: Download the OSM driving network for the service area and compute station-to-station distance/travel-time matrices and route geometries
- **Daily input preparation**: Convert Prophet forecasts into per-day demand files and reduce raw GBFS status snapshots into per-day initial station status
- **Multi-vehicle MIQP**: Pyomo model with per-vehicle capacity, depot stock, per-station buffers, time windows, and an endogenous fleet size via a per-vehicle deployment cost (see [`references/math_model.md`](references/math_model.md))
- **Solver flexibility**: Gurobi by default; factory, time limit, MIP gap, and threads are config keys
- **Result artifacts**: Per-date metrics, station-level results, route tables/shapefiles, and a rebalancing map figure
- **Hydra-composed configs & run tracking**: CLI overrides and `-m` sweeps on every task; each run snapshots its config and log under `LOCAL_DIR/experiments/<task>/`

### Output

- **Processed network** - Station table with integer `idx` indices (depots bracketing the stations), a long-format station-to-station distance/travel-time matrix, route geometries (shapefile), and per-route OSM node sequences
- **Daily model inputs** - Per-day initial station status (bikes available at the start of each day) and per-day integer pickup/dropoff demand
- **Rebalancing plans** - Per-date ordered routes per vehicle (table + shapefile) and per-station operations with initial → final inventory
- **Solve artifacts** - Objective breakdown and solve metrics (distance, squared deviation, vehicles used, MIP gap, status), the exact parameters used, and a route map over a basemap

<br>

## Installation

### Prerequisites

- [pixi](https://pixi.sh) (environment & dependency manager — installs Python 3.11 and the full conda-forge stack; `gurobipy` comes from PyPI)
- A [Gurobi license](https://www.gurobi.com/academia/academic-program-and-licenses/) for the default solver (or switch `solver_params.factory` to another Pyomo-supported solver)

### Steps

1. **Clone the repository**
   ```bash
   git clone https://github.com/jcruz-ferreyra/bluebikes_rebalancing.git
   cd bluebikes_rebalancing
   ```

2. **Install dependencies**
   ```bash
   pixi install
   ```
   This solves and installs the conda-forge environment defined in [`pixi.toml`](pixi.toml) (Python 3.11) and installs `bluebikes_rebalancing` as an editable package.

3. **Set up environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your paths:
   # LOCAL_DIR=/absolute/path/to/your/project/storage   # parent dir that holds data/ and models/
   # DATA_FOLDER=data
   # MODELS_FOLDER=models
   ```
   Tasks resolve their data/model roots from these variables through the Hydra `storage` config group ([`conf/storage/`](bluebikes_rebalancing/conf/storage)); the notebooks use the same variables via [`config.py`](bluebikes_rebalancing/config.py). When `LOCAL_DIR` is not set (e.g. CI), both fall back to the working directory. Pointing `LOCAL_DIR` at the same storage as the forecasting repo lets this pipeline pick up its forecasts directly.

4. **Verify installation**
   ```bash
   pixi run python -c "import bluebikes_rebalancing; print('Installation successful!')"
   ```

<br>

## Quick Start

Run the tasks in the order below; each builds on the previous stage's outputs. The pipeline expects the forecasting repo's outputs under the same `LOCAL_DIR`: station metadata and status snapshots under `data/raw/stations/`, and Prophet forecasts under `data/timeseries_results/forecasts/`.

```mermaid
flowchart LR
    A[prepare_network] --> B[prepare_initial_status]
    A --> C[prepare_demand]
    B --> D[run_optimization]
    C --> D
```

Tasks are configured and launched by [Hydra](https://hydra.cc): every run writes a config snapshot and its log to `LOCAL_DIR/experiments/<task>/<timestamp>/`, any config key can be overridden on the CLI (e.g. `target_date=2026-03-05`), the storage root comes from a config group, and `-m` runs parameter sweeps.

### Storage: local and Colab

- **Local (default)** — outputs land under `LOCAL_DIR` from `.env`.
- **Colab (or any other machine)** — point `LOCAL_DIR` at the mounted Drive and *everything* (tasks, notebooks, experiment runs) follows it:

  ```python
  import os
  os.environ["LOCAL_DIR"] = "/content/drive/MyDrive/bluebikes_analysis"
  ```

  The storage root is a Hydra config group with a single `local` option today; if heavier solving ever moves elsewhere, the plan is dedicated export/ingest tasks plus a new group option — a workflow, not just a path swap.

### Task 1: [prepare_network](bluebikes_rebalancing/tasks/prepare_network)

Downloads the OSM driving network for the service area and computes the station-to-station distance/travel-time matrix and route geometries. Requires `station_information.csv` under `raw/stations/`.

**Configuration**:

Processing Configuration ([`conf/config.yaml`](bluebikes_rebalancing/tasks/prepare_network/conf/config.yaml))

YAML file defining the depot location and the network bounding box:

```yaml
depot_lat_lon: [42.338629, -71.106500]           # [latitude, longitude]

network_bbox: [-71.117, 42.329, -71.078, 42.353]  # [west, south, east, north] in EPSG:4326
```

**Run**:
```bash
pixi run python -m bluebikes_rebalancing.tasks.prepare_network
pixi run python -m bluebikes_rebalancing.tasks.prepare_network 'depot_lat_lon=[42.34,-71.10]'  # alternative depot
```

**Output** (saved under `LOCAL_DIR/data/processed/`):
- `stations/station_information.csv` - Stations of interest with assigned `idx` indices
- `network/dist_ttime_long.csv` - Long-format origin/destination distance and travel-time matrix
- `network/routes_long_wgs84/` - Route geometries shapefile (WGS84)
- `network/routes_node_sequences.json` - Per-route OSM node sequences

---

### Task 2: [prepare_initial_status](bluebikes_rebalancing/tasks/prepare_initial_status)

Reduces the raw GBFS status snapshots into one initial-status file per day for the configured range. Requires the raw station files and the processed station info from `prepare_network`.

**Configuration**:

Processing Configuration ([`conf/config.yaml`](bluebikes_rebalancing/tasks/prepare_initial_status/conf/config.yaml))

YAML file defining the date range:

```yaml
status_start_date: "2026-03-01"  # YYYY-MM-DD - first day to generate status file
status_end_date: "2026-03-31"    # YYYY-MM-DD - last day to generate status file
```

**Run**:
```bash
pixi run python -m bluebikes_rebalancing.tasks.prepare_initial_status
pixi run python -m bluebikes_rebalancing.tasks.prepare_initial_status status_start_date=2026-04-01 status_end_date=2026-04-07
```

**Output** (saved to `LOCAL_DIR/data/processed/initial_status/`):
- `initial_status_<YYYYMMDD>.csv` - Per-station bike counts at the start of each day (`idx`, `short_name`, `initial_status`)

---

### Task 3: [prepare_demand](bluebikes_rebalancing/tasks/prepare_demand)

Converts per-station forecast files into one demand file per day, rounding to integers and capping negatives at zero. Requires the forecasting repo's `*_forecast.csv` files and the processed station info.

**Configuration**:

Processing Configuration ([`conf/config.yaml`](bluebikes_rebalancing/tasks/prepare_demand/conf/config.yaml))

YAML file defining the forecast source and date range:

```yaml
model_name: "prophet"            # forecast source under timeseries_results/forecasts/

demand_start_date: "2026-03-01"  # YYYY-MM-DD - first day to generate demand file
demand_end_date: "2026-03-31"    # YYYY-MM-DD - last day to generate demand file
```

**Run**:
```bash
pixi run python -m bluebikes_rebalancing.tasks.prepare_demand
pixi run python -m bluebikes_rebalancing.tasks.prepare_demand demand_start_date=2026-05-01 demand_end_date=2026-05-31
```

**Output** (saved to `LOCAL_DIR/data/processed/demand/`):
- `demand_<YYYYMMDD>.csv` - Per-station integer pickups/dropoffs forecasts for the day (`idx`, `station_id`, `pickups_forecast`, `dropoffs_forecast`)

---

### Task 4: [run_optimization](bluebikes_rebalancing/tasks/run_optimization)

Builds and solves the multi-vehicle rebalancing MIQP for one target date, then writes metrics, station results, routes, and a map figure. Requires all previous tasks' outputs for the target date.

**Configuration**:

Processing Configuration ([`conf/config.yaml`](bluebikes_rebalancing/tasks/run_optimization/conf/config.yaml))

YAML file defining the target date, model parameters, solver, and plotting:

```yaml
target_date: "2026-03-03"    # YYYY-MM-DD format

model_params:
  truck_capacity: 20         # Q: per-vehicle capacity in bikes
  fleet_size: 3              # K: maximum number of vehicles that may be used
  depot_capacity: 20         # S: total bikes the fleet can source/return at the depot
  buffer: 2                  # B: minimum bikes and docks at each station after rebalancing
  alpha: 1.0                 # distance cost weight ($/meter)
  beta: 10.0                 # service quality weight ($/bike²)
  gamma: 1000.0              # fixed cost per deployed vehicle (makes fleet size endogenous)
  service_time: 5.0          # fixed time per station stop (minutes)
  time_per_bike: 1.0         # variable time per bike loaded/unloaded (minutes)
  max_operation_time: 180.0  # T_MAX: per-vehicle operational window (minutes)

solver_params:
  factory: "gurobi"          # "gurobi", "cplex", or "glpk"
  time_limit: 600            # solver time limit in seconds
  mip_gap: 0.02              # relative MIP optimality gap
  threads: 8                 # number of solver threads

plot_params:
  save_plot: true            # whether to save the rebalancing map
  zoom: 15                   # basemap tile zoom level
```

**Run**:
```bash
pixi run python -m bluebikes_rebalancing.tasks.run_optimization
pixi run python -m bluebikes_rebalancing.tasks.run_optimization target_date=2026-03-05
pixi run python -m bluebikes_rebalancing.tasks.run_optimization model_params.beta=100 model_params.fleet_size=2
# sweep the deployment cost (one hydra job per value):
pixi run python -m bluebikes_rebalancing.tasks.run_optimization -m model_params.gamma=1,10,100,1000
```

**Output** (saved to `LOCAL_DIR/data/rebalancing_results/results/<YYYYMMDD>/`):
- `parameters.json` - The exact model/solver parameters used for the run
- `results_metrics.json` - Objective terms and solve metrics (distance, deviation, vehicles used, status)
- `results_stations.csv` - Per-station initial status, target, pickups/dropoffs, and final status
- `route.csv` / `route/` - Ordered route legs per vehicle (table + shapefile)
- `rebalancing_map.jpg` - Route map over a basemap (when `plot_params.save_plot: true`)

<br>

## Bonus: [Analysis Notebooks](notebooks/)

Jupyter notebooks for route inspection and parametric analysis. The notebook toolchain (JupyterLab, ipykernel) lives in the **`dev`** environment; the `lab` and `kernel` tasks are defined there, so a bare `pixi run` picks it automatically:

```bash
pixi run lab       # launch JupyterLab (provisions the dev environment on first run)
pixi run kernel    # one-time: register the "Pixi (bluebikes_rebalancing)" kernel for VS Code / Jupyter
```

**Flow** (`notebooks/`):
- `01_calculate_routes` - Inspect the network matrices and route geometries
- `02_parametric_analysis` - Sweep objective weights (e.g. beta) across dates and compare distance/service trade-offs
- `03_run_optimization` - Interactive model building and solving

<br>

## Structure

### Source Layout

```
bluebikes_rebalancing/
├── bluebikes_rebalancing/           # source package
│   ├── config.py                    # path/secrets resolver for the notebooks (.env, CI-aware)
│   ├── conf/
│   │   └── storage/                 # shared hydra config group: local.yaml
│   ├── model/                       # Pyomo MIQP: variables, objective, constraints
│   ├── plots/
│   │   └── plots.py                 # shared plotting helpers (COLORS, rebalancing map, …)
│   └── tasks/                       # four runnable pipeline stages
│       ├── prepare_network/
│       ├── prepare_initial_status/
│       ├── prepare_demand/
│       └── run_optimization/
├── notebooks/                       # route inspection & parametric analysis (01 → 03)
├── data/                            # CCDS data dirs (real data lives under LOCAL_DIR)
├── references/
│   └── math_model.md                # MIQP formulation
├── reports/figures/                 # generated figures
├── pixi.toml                        # conda-forge environment, features & tasks
├── pixi.lock
└── pyproject.toml                   # packaging metadata (flit)
```

Each task folder follows a consistent structure:

```
run_optimization/
├── __init__.py                 # exports the Context model + entry function
├── __main__.py                 # @hydra.main entry point — composes the config, builds the Context, runs the task
├── conf/
│   └── config.yaml             # task parameters + hydra job/run/sweep settings
├── types.py                    # pydantic Context model: validation + computed I/O paths
└── run_optimization.py         # core logic (with module-level helper functions)
```

### Config & Context Pattern

Two layers share the work. **Hydra** composes each task's config (`conf/config.yaml` + the shared `storage` group + any CLI overrides) and owns logging and the per-run output dir. The entrypoint feeds the composed config straight into the task's **pydantic Context model** — `types.py` is each task's contract: field types and constraints replace hand-written checks, validators cover the cross-field rules, and `@property` methods compute — and create on access — every input/output path. The data layout below is therefore defined literally by those properties.

```python
class PrepareDemandContext(BaseModel):
    """Context for preparing daily demand forecast files."""

    model_config = ConfigDict(extra="forbid")   # unknown config keys are rejected

    # --- config (from conf/config.yaml, composed by hydra) ---
    model_name: str
    demand_start_date: str                      # YYYY-MM-DD
    demand_end_date: str                        # YYYY-MM-DD
    output_data_dir: Path                       # storage group: data_dir

    @field_validator("demand_start_date", "demand_end_date")
    @classmethod
    def _check_date_format(cls, value: str) -> str:
        ...  # real calendar date in YYYY-MM-DD

    # --- computed I/O paths ---
    @property
    def forecasts_dir(self) -> Path:              # input
        return self.output_data_dir / "timeseries_results" / "forecasts" / self.model_name

    @property
    def demand_dir(self) -> Path:                 # output (created on access)
        path = self.output_data_dir / "processed" / "demand"
        path.mkdir(parents=True, exist_ok=True)
        return path
```

This split provides:
- Hydra owns composition, CLI overrides, sweeps, job logging, and per-run experiment outputs
- Pydantic owns validation: field-named errors before any task logic runs, with `extra="forbid"` catching config typos (including nested `model_params` keys)
- Side-effect-free construction — output directories are created lazily on first property access
- A clean split between user-facing config (`conf/config.yaml`) and on-disk layout

### Data Layout

Produced by the pipeline under the storage directory (`LOCAL_DIR/DATA_FOLDER`, i.e. `data/`); inputs marked *(forecasting repo)* are produced by the companion project sharing the same `LOCAL_DIR`:

```
data/
├── raw/
│   └── stations/
│       ├── station_information.csv                  # (forecasting repo) station metadata
│       ├── stations_of_interest.json                # manual input (station short_name IDs)
│       └── status/
│           └── station_status_<YYMMDD_HHMMSS>.csv   # (forecasting repo) status snapshots
├── timeseries_results/
│   └── forecasts/prophet/
│       └── <station_id>_forecast.csv                # (forecasting repo) demand forecasts
├── processed/
│   ├── stations/station_information.csv             # prepare_network (adds idx)
│   ├── network/                                     # prepare_network
│   │   ├── dist_ttime_long.csv
│   │   ├── routes_long_wgs84/
│   │   └── routes_node_sequences.json
│   ├── initial_status/
│   │   └── initial_status_<YYYYMMDD>.csv            # prepare_initial_status
│   └── demand/
│       └── demand_<YYYYMMDD>.csv                    # prepare_demand
└── rebalancing_results/
    └── results/<YYYYMMDD>/                          # run_optimization
        ├── parameters.json
        ├── results_metrics.json
        ├── results_stations.csv
        ├── route.csv
        ├── route/
        └── rebalancing_map.jpg

experiments/                                         # hydra run tracking, per task
└── <task>/
    ├── <timestamp>/                                 # one dir per run: .hydra/ config snapshot + job log
    └── multirun/<timestamp>/<job#>/                 # -m sweep runs
```

<br>

## How It Works

### Task 1: [prepare_network](bluebikes_rebalancing/tasks/prepare_network)

Downloads the OSM driving network for the service area and turns it into a station-to-station distance/travel-time matrix with route geometries.

<details>
<summary><b>Details</b></summary>
<br>

**Processing Pipeline**:
1. Load & Filter Stations
   - Read `stations_of_interest.json`, filter `station_information.csv` to those `short_name`s, keep `lat` / `lon` / `capacity`
2. Validate Coverage
   - Assert the depot and every station fall inside `network_bbox` — otherwise routing would silently snap to spurious nearest nodes
3. Station Table
   - Prepend `depot_start` and append `depot_end` (both at the depot coordinate, capacity NA) and assign integer `idx`
4. Download & Calibrate Network
   - `osmnx.graph_from_bbox(network_type="drive")`, add edge speeds, apply a Boston-calibrated speed adjustment, recompute travel times
5. Routes for Every OD Pair
   - Cross-join stations + depots into all origin/destination pairs (minus the diagonal); snap each endpoint to the nearest node; shortest path weighted by `travel_time`
6. Geometry & Metrics
   - Convert each node sequence to a LineString; sum edge `length` and `travel_time` into `dist_m` / `ttime_s`
7. Save
   - Distance/travel-time CSV, routes shapefile, route node-sequence JSON, and the station-information CSV

**Key Algorithms**:
- **Speed calibration**: a piecewise multiplier on OSM `speed_kph` (≥50 → ×0.85, 42–50 → ×0.65, 35–50 → ×0.55), tuned for Boston so travel times reflect real surface-street speeds
- **Travel-time shortest paths**: routes minimize travel time, not raw distance
- **Depot bracketing**: `depot_start` (idx 0) and `depot_end` (idx N+1) share the depot coordinate, framing the stations in the index

**Technical Details**:
- Network is `drive`, `simplify=True`, `truncate_by_edge=True`
- Distance validation reprojects to NAD83 Massachusetts (EPSG:26986) and compares against summed edge length — region-specific, warned in the logs
- Single-node routes (endpoints that snap to the same node) become zero-length LineStrings with 0 distance/time
- The speed calibration and validation projection are Boston-specific; both emit warnings to retune elsewhere

</details>

---

### Task 2: [prepare_initial_status](bluebikes_rebalancing/tasks/prepare_initial_status)

Reduces the raw GBFS status snapshots into one initial-status file per day.

<details>
<summary><b>Details</b></summary>
<br>

**Processing Pipeline**:
1. Station Mapping
   - Join `stations_of_interest.json` → raw `station_information.csv` (`station_id` ↔ `short_name`) → processed station info (`idx`); unmatched stations are warned and dropped
2. Date Range
   - Expand `status_start_date` → `status_end_date` into daily timestamps
3. Earliest Snapshot per Day
   - Glob `station_status_*.csv`, parse the `<YYMMDD_HHMMSS>` timestamp, group by date, and pick the earliest file (closest to the start of the day)
4. Per-Day Reduction
   - Keep installed & renting stations (`is_installed == 1 & is_renting == 1`), merge the mapping, take `num_bikes_available` as `initial_status`
5. Save
   - `initial_status_<YYYYMMDD>.csv` (`idx`, `short_name`, `initial_status`), sorted by `idx`

**Key Features**:
- **Earliest-of-day selection**: the first snapshot each day approximates the overnight starting inventory
- **Operational filter**: only installed and renting stations contribute
- **Missing-day handling**: dates without a snapshot are logged and skipped, not zero-filled

**Technical Details**:
- Filenames are parsed as `station_status_<YYMMDD>_<HHMMSS>.csv`, with `20`+`YY` for the year
- The mapping merge is an inner join on `station_id`, so only mapped stations of interest survive
- `initial_status = num_bikes_available`

</details>

---

### Task 3: [prepare_demand](bluebikes_rebalancing/tasks/prepare_demand)

Converts the companion repo's per-station forecasts into one integer demand file per day.

<details>
<summary><b>Details</b></summary>
<br>

**Processing Pipeline**:
1. Load Metadata
   - Read the processed `station_information.csv` for the `short_name` → `idx` map
2. Load Forecasts
   - Glob `*_forecast.csv` under `timeseries_results/forecasts/<model_name>/`, parse `ds`, key by station
3. Date Range
   - Expand `demand_start_date` → `demand_end_date` into daily timestamps
4. Per-Day Demand
   - For each station take the row at `ds == target_date`; round `pickups_forecast` / `dropoffs_forecast` to integers and clamp negatives to 0; stations missing that date are warned
5. Index & Save
   - Merge `idx`, order `idx, station_id, pickups_forecast, dropoffs_forecast`, write `demand_<YYYYMMDD>.csv`

**Key Features**:
- **Forecast-source agnostic**: `model_name` selects the forecasts subdirectory (e.g. `prophet`)
- **Integer, non-negative demand**: rounded and floored at 0 to feed the integer model
- **Per-day files**: one file per date, matching the optimizer's `target_date` interface

**Technical Details**:
- Reads `<station_id>_forecast.csv` (Prophet `pickups_forecast` / `dropoffs_forecast`) from the companion project's outputs
- Raises if a date has no station forecasts at all; warns and skips individual stations missing that date
- Net demand `d_i = dropoffs − pickups` (and the target `t_i = c_i/2 − d_i`) is derived later inside the optimizer, not here

</details>

---

### Task 4: [run_optimization](bluebikes_rebalancing/tasks/run_optimization)

Builds and solves the multi-vehicle rebalancing MIQP for one target date, then writes metrics, station results, routes, and a map.

<details>
<summary><b>Details</b></summary>
<br>

**Processing Pipeline**:
1. Load & Merge Inputs
   - Station info + capacities, that date's initial status and demand, the distance/travel-time matrix and route geometries; set both depots' inventory/capacity to `Q`
2. Build Model
   - Assemble nodes/arcs and `b` / `c` / `t` (`t_i = c_i/2 − d_i`); call `build_vrp_model` (per-vehicle `x, u, v, w`; station-level `b_final, y, p`)
3. Solve
   - Hand the model to the configured solver (Gurobi) with the time limit, MIP gap, and thread count
4. Extract
   - Per-vehicle routes ordered from the depot, fleet-aggregated station operations, the objective breakdown (routing / service / deployment), time components, vehicles used, and MIP gap
5. Save
   - `parameters.json`, `results_metrics.json`, `results_stations.csv`, `route.csv` + shapefile, and the rebalancing map

**Key Algorithms**:
- **Multi-vehicle MIQP**: minimize α·distance + β·Σ(b_final − t)² + γ·(vehicles used), subject to routing, flow conservation, subtour elimination, per-vehicle load tracking, station buffers, per-vehicle time budgets, depot capacity, and symmetry breaking — full formulation in [`references/math_model.md`](references/math_model.md)
- **Endogenous fleet size**: the per-vehicle deployment cost γ means a van is deployed only when its routing + service benefit beats γ
- **Lifted Desrochers–Laporte MTZ**: tightens the LP relaxation versus basic MTZ (it forbids fractional two-station loops) without cutting any integer route
- **Per-vehicle route map**: each van's legs drawn in its own color, with per-stop net operations and per-vehicle depot load/return labels

**Technical Details**:
- The quadratic deviation penalty makes this a MIQP (QP objective); depots are `depot_start` (node 0, inventory `Q`) and `depot_end` (node N+1, absorbs returns), with `S = depot_capacity` capping fleet sourcing/return
- Per-vehicle load tracking uses node-indexed big-M; the time budget charges travel + per-stop service + per-bike handling, including the depot load and return
- Setting `model_params.fleet_size: 1` (with `depot_capacity` = `truck_capacity`) reproduces the single-vehicle case closely
- Results land under `rebalancing_results/results/<YYYYMMDD>/`

</details>

<br>

## 👥 Contributors
<!-- Add one entry per contributor:
<a href="https://github.com/USERNAME"><img src="https://github.com/USERNAME.png" width="60" height="60" alt="USERNAME"/></a>
-->
<a href="https://github.com/jcruz-ferreyra"><img src="https://github.com/jcruz-ferreyra.png?size=120" width="60" height="60" alt="jcruz-ferreyra"/></a>

<br>

## Additional Resources

### Related Technologies

- **[Pyomo](http://www.pyomo.org/)** - Algebraic modeling language used to build the MIQP
- **[Gurobi](https://www.gurobi.com/)** - Default MIP/MIQP solver (swap via `solver_params.factory`)
- **[OSMnx](https://osmnx.readthedocs.io/) / [OpenStreetMap](https://www.openstreetmap.org/)** - Driving-network download and shortest-path routing
- **[GeoPandas](https://geopandas.org/) / [Shapely](https://shapely.readthedocs.io/)** - Route geometries and spatial outputs
- **[contextily](https://contextily.readthedocs.io/)** - Basemap tiles for the rebalancing map
- **[Hydra](https://hydra.cc/)** - Config composition, CLI overrides, and multirun sweeps
- **[pixi](https://pixi.sh/)** - conda-forge environment and task runner
- **[Cookiecutter Data Science](https://cookiecutter-data-science.drivendata.org/)** - Project template this layout is based on

### Support

For questions or issues:
- **GitHub Issues**: [bluebikes_rebalancing/issues](https://github.com/jcruz-ferreyra/bluebikes_rebalancing/issues)

### Citation

If you use this optimizer in your research, please cite:
```bibtex
@software{bluebikes_rebalancing_2026,
  title       = {BlueBikes Rebalancing: Multi-Vehicle Station Rebalancing Optimization for Boston Bike-Share},
  author      = {Ferreyra, Juan Cruz},
  institution = {Northeastern University},
  year        = {2026},
  url         = {https://github.com/jcruz-ferreyra/bluebikes_rebalancing}
}
```

### License

MIT License - see [LICENSE](LICENSE) file for details.
