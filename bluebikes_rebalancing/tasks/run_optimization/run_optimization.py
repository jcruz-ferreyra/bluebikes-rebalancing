# tasks/run_optimization/run_optimization.py

import json
import logging

import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd
from pyomo.environ import SolverFactory, value

from bluebikes_rebalancing.model import build_vrp_model
from bluebikes_rebalancing.plots import plot_rebalancing_map

from .types import RunOptimizationContext

logger = logging.getLogger(__name__)

# Depot node names (architectural constants)
DEPOT_START = "depot_start"
DEPOT_END = "depot_end"


# ============================================================================
# Helper functions
# ============================================================================


def _load_and_prepare_data(ctx: RunOptimizationContext) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Load and merge all input data into station and network DataFrames.

    Args:
        ctx: RunOptimizationContext with paths and configuration

    Returns:
        Tuple of (stations_df, network_df)
            - stations_df: idx, short_name, lat, lon, capacity, initial_status,
                          pickups_forecast, dropoffs_forecast, net_demand
            - network_df: origin, dest, dist_m, ttime_min, geometry
    """
    logger.info("=" * 60)
    logger.info("Loading input data")
    logger.info("=" * 60)

    # Load station metadata
    stations_df = pd.read_csv(ctx.station_info_path)
    logger.info(f"✓ Loaded station metadata: {len(stations_df)} entries")

    # Load initial status for target date
    initial_status_df = pd.read_csv(ctx.initial_status_path)
    logger.info(f"✓ Loaded initial status: {len(initial_status_df)} stations")

    # Load demand forecast for target date
    demand_df = pd.read_csv(ctx.demand_path)

    if "station_id" in demand_df.columns and "short_name" not in demand_df.columns:
        demand_df = demand_df.rename(columns={"station_id": "short_name"})

    demand_df["net_demand"] = demand_df["dropoffs_forecast"] - demand_df["pickups_forecast"]
    logger.info(f"✓ Loaded demand forecast: {len(demand_df)} stations")

    # Load network distance/travel time matrix
    network_df = pd.read_csv(ctx.dist_ttime_path)
    network_df["ttime_min"] = network_df["ttime_s"] / 60
    logger.info(f"✓ Loaded network matrix: {len(network_df)} arcs")

    # Load route geometries
    routes_gdf = gpd.read_file(ctx.routes_shapefile_path)
    logger.info(f"✓ Loaded route geometries: {len(routes_gdf)} routes")

    # --- Prepare station DataFrame ---
    # Filter stations to active ones (those with initial status) and depots
    active_stations = initial_status_df["short_name"].tolist()
    active_with_depots = active_stations + [DEPOT_START, DEPOT_END]
    stations_df = stations_df[stations_df["short_name"].isin(active_with_depots)].copy()

    # Merge initial status and demand
    stations_df = stations_df.merge(
        initial_status_df[["idx", "short_name", "initial_status"]],
        on=["idx", "short_name"],
        how="left",
    )
    stations_df = stations_df.merge(
        demand_df[["idx", "short_name", "pickups_forecast", "dropoffs_forecast", "net_demand"]],
        on=["idx", "short_name"],
        how="left",
    )

    # Set depot values
    Q = ctx.model_params["truck_capacity"]

    filt_depot_start = stations_df["short_name"] == DEPOT_START
    filt_depot_end = stations_df["short_name"] == DEPOT_END

    # Depot start: capacity = Q, initial_status = Q (can supply full truck)
    stations_df.loc[filt_depot_start, ["capacity", "initial_status"]] = Q

    # Depot end: capacity = Q, initial_status = 0 (can absorb full truck)
    stations_df.loc[filt_depot_end, "capacity"] = Q
    stations_df.loc[filt_depot_end, "initial_status"] = 0

    logger.info(
        f"✓ Prepared station data: {len(stations_df)} nodes ({len(active_stations)} stations + 2 depots)"
    )

    # --- Prepare network DataFrame ---
    # Map indices to station names
    idx_to_name = stations_df.set_index("idx")["short_name"].to_dict()
    network_df["origin"] = network_df["origin_idx"].map(idx_to_name)
    network_df["dest"] = network_df["dest_idx"].map(idx_to_name)

    # Filter to active stations and depots only
    active_nodes = stations_df["short_name"].tolist()
    network_df = network_df[
        network_df["origin"].isin(active_nodes) & network_df["dest"].isin(active_nodes)
    ].copy()

    logger.info(f"✓ Filtered network to active arcs: {len(network_df)} arcs")

    # Merge with route geometries
    routes_gdf["origin"] = routes_gdf["origin_idx"].map(idx_to_name)
    routes_gdf["dest"] = routes_gdf["dest_idx"].map(idx_to_name)

    network_df = network_df.merge(
        routes_gdf[["origin", "dest", "geometry"]], on=["origin", "dest"], how="left"
    )

    # Create GeoDataFrame
    network_df = gpd.GeoDataFrame(network_df, geometry="geometry", crs="EPSG:4326")

    logger.info(f"✓ Prepared network data: {len(network_df)} arcs with geometries")

    return stations_df, network_df


def _build_model(stations_df: pd.DataFrame, network_df: pd.DataFrame, ctx: RunOptimizationContext):
    """
    Build Pyomo optimization model from prepared data.

    Args:
        stations_df: DataFrame with station data
        network_df: DataFrame with network data
        ctx: RunOptimizationContext with model parameters

    Returns:
        Pyomo ConcreteModel ready to solve
    """
    logger.info("=" * 60)
    logger.info("Building optimization model")
    logger.info("=" * 60)

    # Extract model parameters
    Q = ctx.model_params["truck_capacity"]
    B = ctx.model_params["buffer"]
    ALPHA = ctx.model_params["alpha"]
    BETA = ctx.model_params["beta"]
    SERVICE_TIME = ctx.model_params["service_time"]
    TIME_PER_BIKE = ctx.model_params["time_per_bike"]
    T_MAX = ctx.model_params["max_operation_time"]

    # Define node sets
    nodes = stations_df["short_name"].tolist()
    stations = [n for n in nodes if n not in [DEPOT_START, DEPOT_END]]

    logger.info(f"Nodes: {len(nodes)} ({len(stations)} stations + 2 depots)")

    # Initial inventory dictionary
    b = stations_df.set_index("short_name")["initial_status"].to_dict()

    # Capacity dictionary
    c = stations_df.set_index("short_name")["capacity"].to_dict()

    # Net demand and target inventory (stations only)
    d = stations_df.set_index("short_name")["net_demand"].to_dict()
    t = {i: c[i] / 2 - d[i] for i in stations}

    # Distance and travel time dictionaries
    dist = {(row.origin, row.dest): row.dist_m for row in network_df.itertuples()}
    ttime = {(row.origin, row.dest): row.ttime_min for row in network_df.itertuples()}

    logger.info(f"Network arcs: {len(dist)}")
    logger.info(
        f"Initial deviations from target: mean={sum(b[i] - t[i] for i in stations) / len(stations):.1f} bikes"
    )

    # Build model
    model = build_vrp_model(
        nodes=nodes,
        stations=stations,
        b=b,
        c=c,
        t=t,
        dist=dist,
        ttime=ttime,
        Q=Q,
        B=B,
        T_MAX=T_MAX,
        ALPHA=ALPHA,
        BETA=BETA,
        SERVICE_TIME=SERVICE_TIME,
        TIME_PER_BIKE=TIME_PER_BIKE,
    )

    logger.info("✓ Model built successfully")

    return model


def _solve_model(model, ctx: RunOptimizationContext):
    """
    Solve optimization model using configured solver.

    Args:
        model: Pyomo ConcreteModel to solve
        ctx: RunOptimizationContext with solver parameters

    Returns:
        Solver result object
    """
    logger.info("=" * 60)
    logger.info("Solving optimization model")
    logger.info("=" * 60)

    # Extract solver parameters
    solver_factory = ctx.solver_params["factory"]
    time_limit = ctx.solver_params["time_limit"]
    mip_gap = ctx.solver_params["mip_gap"]
    threads = ctx.solver_params["threads"]

    logger.info(f"Solver: {solver_factory}")
    logger.info(f"Time limit: {time_limit}s")
    logger.info(f"MIP gap: {mip_gap * 100}%")
    logger.info(f"Threads: {threads}")

    # Initialize solver
    solver = SolverFactory(solver_factory)
    solver.options["TimeLimit"] = time_limit
    solver.options["MIPGap"] = mip_gap
    solver.options["Threads"] = threads

    # Solve
    result = solver.solve(model, tee=False)

    logger.info(f"✓ Solver completed: {result.solver.status}")
    logger.info(f"  Termination condition: {result.solver.termination_condition}")

    return result


def _order_route_by_sequence(route_df: pd.DataFrame) -> pd.DataFrame:
    """Order route dataframe by visit sequence starting from depot_start."""
    ordered = []
    current = DEPOT_START

    while len(ordered) < len(route_df):
        arc = route_df[route_df["from"] == current]
        if arc.empty:
            break
        ordered.append(arc.iloc[0])
        current = arc.iloc[0]["to"]

    return pd.DataFrame(ordered).reset_index(drop=True)


def _save_parameters(model, ctx: RunOptimizationContext) -> None:
    """Save model and solver parameters to JSON."""
    parameters = {
        "target_date": ctx.target_date,
        "truck_capacity": ctx.model_params["truck_capacity"],
        "buffer": ctx.model_params["buffer"],
        "alpha": ctx.model_params["alpha"],
        "beta": ctx.model_params["beta"],
        "service_time": ctx.model_params["service_time"],
        "time_per_bike": ctx.model_params["time_per_bike"],
        "max_operation_time": ctx.model_params["max_operation_time"],
        "solver_factory": ctx.solver_params["factory"],
        "solver_time_limit": ctx.solver_params["time_limit"],
        "solver_mip_gap": ctx.solver_params["mip_gap"],
        "solver_threads": ctx.solver_params["threads"],
        "num_stations": len(model.STATIONS),
        "num_nodes": len(model.NODES),
        "big_M": value(model.M),
    }

    with open(ctx.results_dir / "parameters.json", "w") as f:
        json.dump(parameters, f, indent=2)

    logger.info("✓ Saved parameters.json")


def _save_metrics(model, result, ctx: RunOptimizationContext) -> None:
    """Save optimization metrics to JSON."""
    # Extract objective components
    routing_cost = value(model.alpha) * sum(
        value(model.dist[i, j]) * value(model.x[i, j]) for (i, j) in model.ARCS
    )
    service_penalty = value(model.beta) * sum(
        (value(model.b_final[i]) - value(model.t[i])) ** 2 for i in model.STATIONS
    )
    total_objective = value(model.obj)

    # Extract time components
    travel_time = sum(value(model.ttime[i, j]) * value(model.x[i, j]) for (i, j) in model.ARCS)
    station_time = sum(
        value(model.s) * sum(value(model.x[i_arc, j]) for (i_arc, j) in model.ARCS if i_arc == i)
        + value(model.tau) * (value(model.u[i]) + value(model.v[i]))
        for i in model.STATIONS
    )
    depot_time = value(model.tau) * (value(model.u[DEPOT_START]) + value(model.v[DEPOT_END]))
    total_time = travel_time + station_time + depot_time

    # Extract distance
    total_distance_m = sum(value(model.dist[i, j]) * value(model.x[i, j]) for (i, j) in model.ARCS)

    # Extract MIP gap
    try:
        obj_bound = float(result.problem.lower_bound)
        obj_value = float(result.problem.upper_bound)
        mip_gap = abs(obj_value - obj_bound) / abs(obj_value)
        mip_gap_pct = mip_gap * 100
    except (AttributeError, TypeError, ZeroDivisionError):
        mip_gap_pct = None

    # Count visited stations
    num_visited = sum(
        1
        for i in model.STATIONS
        if sum(value(model.x[i_arc, j]) for (i_arc, j) in model.ARCS if i_arc == i) > 0.5
    )

    # Count total bikes moved
    total_bikes_moved = sum(value(model.u[i]) for i in model.NODES)

    # Calculate deviation metrics
    initial_squared_deviation = sum(
        (value(model.b[i]) - value(model.t[i])) ** 2 for i in model.STATIONS
    )
    final_squared_deviation = sum(
        (value(model.b_final[i]) - value(model.t[i])) ** 2 for i in model.STATIONS
    )

    initial_mae_deviation = sum(
        abs(value(model.b[i]) - value(model.t[i])) for i in model.STATIONS
    ) / len(model.STATIONS)
    final_mae_deviation = sum(
        abs(value(model.b_final[i]) - value(model.t[i])) for i in model.STATIONS
    ) / len(model.STATIONS)

    results_metrics = {
        "solver_status": str(result.solver.status),
        "termination_condition": str(result.solver.termination_condition),
        "objective_value": round(total_objective, 2),
        "mip_gap_percent": round(mip_gap_pct, 2) if mip_gap_pct is not None else None,
        "routing_cost": round(routing_cost, 1),
        "service_penalty": round(service_penalty, 1),
        "total_distance_m": round(total_distance_m, 1),
        "total_distance_km": round(total_distance_m / 1000, 3),
        "initial_squared_deviation": round(initial_squared_deviation, 1),
        "final_squared_deviation": round(final_squared_deviation, 1),
        "initial_mae_deviation": round(initial_mae_deviation, 2),
        "final_mae_deviation": round(final_mae_deviation, 2),
        "total_operation_time_min": round(total_time, 1),
        "travel_time_min": round(travel_time, 1),
        "station_time_min": round(station_time, 1),
        "depot_time_min": round(depot_time, 1),
        "total_bikes_moved": int(total_bikes_moved),
        "num_stations_visited": num_visited,
        "num_stations_available": len(model.STATIONS),
    }

    with open(ctx.results_dir / "results_metrics.json", "w") as f:
        json.dump(results_metrics, f, indent=2)

    logger.info("✓ Saved results_metrics.json")


def _save_stations(model, ctx: RunOptimizationContext) -> None:
    """Save station-level results to CSV."""
    ops_records = []
    for i in model.NODES:
        record = {
            "short_name": i,
            "capacity": int(value(model.c[i])),
            "target": value(model.t[i]) if i in model.STATIONS else None,
            "initial": int(value(model.b[i])),
            "pickups": int(value(model.u[i])),
            "dropoffs": int(value(model.v[i])),
            "final": int(value(model.b_final[i])),
        }

        # Calculate deviations
        if i in model.STATIONS:
            record["initial_deviation"] = value(model.t[i]) - value(model.b[i])
            record["final_deviation"] = value(model.t[i]) - value(model.b_final[i])
        else:
            record["initial_deviation"] = None
            record["final_deviation"] = None

        # Check if visited
        visited = sum(value(model.x[i_arc, j]) for (i_arc, j) in model.ARCS if i_arc == i) > 0.5
        record["visited"] = int(visited)

        ops_records.append(record)

    results_stations = pd.DataFrame(ops_records)
    results_stations.to_csv(ctx.results_dir / "results_stations.csv", index=False)

    logger.info("✓ Saved results_stations.csv")


def _save_route(model, network_df: gpd.GeoDataFrame, ctx: RunOptimizationContext) -> None:
    """Save route to CSV and shapefile."""
    # Build route dataframe
    route_records = [
        {
            "from": i,
            "to": j,
            "pickups": int(value(model.u[i])),
            "dropoffs": int(value(model.v[i])),
            "load_leave": int(value(model.w[i])),
        }
        for (i, j) in model.ARCS
        if value(model.x[i, j]) > 0.5
    ]

    route_df = pd.DataFrame(route_records)

    # Order by sequence
    route_df = _order_route_by_sequence(route_df)

    # Save CSV
    route_df.to_csv(ctx.results_dir / "route.csv", index=False)
    logger.info("✓ Saved route.csv")

    # Merge with network geometries
    route_with_geom = route_df.merge(
        network_df[["origin", "dest", "geometry"]],
        left_on=["from", "to"],
        right_on=["origin", "dest"],
        how="left",
    )

    # Drop redundant columns and create GeoDataFrame
    route_with_geom = route_with_geom.drop(columns=["origin", "dest"])
    route_gdf = gpd.GeoDataFrame(route_with_geom, geometry="geometry", crs="EPSG:4326")

    # Save shapefile
    route_shp_dir = ctx.results_dir / "route"
    route_shp_dir.mkdir(exist_ok=True)
    route_gdf.to_file(route_shp_dir / "route.shp")

    logger.info("✓ Saved route shapefile")


def _save_map(
    model, stations_df: pd.DataFrame, network_df: gpd.GeoDataFrame, ctx: RunOptimizationContext
) -> None:
    """Save rebalancing map visualization."""

    # Prepare station plot dataframe (stations only, no depots)
    plot_records = []
    for i in model.STATIONS:
        plot_records.append(
            {
                "station": i,
                "lat": stations_df[stations_df["short_name"] == i]["lat"].values[0],
                "lon": stations_df[stations_df["short_name"] == i]["lon"].values[0],
                "deviation": value(model.b[i]) - value(model.t[i]),
                "pickups": int(value(model.u[i])),
                "dropoffs": int(value(model.v[i])),
            }
        )
    plot_df = pd.DataFrame(plot_records)

    # Build ordered route dataframe
    route_records = [
        {
            "from": i,
            "to": j,
            "pickups": int(value(model.u[i])),
            "dropoffs": int(value(model.v[i])),
        }
        for (i, j) in model.ARCS
        if value(model.x[i, j]) > 0.5
    ]
    route_df = pd.DataFrame(route_records)
    route_df = _order_route_by_sequence(route_df)

    # Prepare journey geodataframe (ordered arcs traveled)
    journey_gdf = route_df.merge(
        network_df[["origin", "dest", "geometry"]],
        left_on=["from", "to"],
        right_on=["origin", "dest"],
        how="left",
    )
    journey_gdf = journey_gdf.drop(columns=["origin", "dest"])
    journey_gdf = gpd.GeoDataFrame(journey_gdf, geometry="geometry", crs="EPSG:4326")

    # Prepare depot dataframe
    depot_lat = stations_df[stations_df["short_name"] == DEPOT_START]["lat"].values[0]
    depot_lon = stations_df[stations_df["short_name"] == DEPOT_START]["lon"].values[0]
    depot_df = pd.DataFrame([{"lat": depot_lat, "lon": depot_lon}])

    # Depot operations
    depot_ops = {
        "pickups": int(value(model.u[DEPOT_START])),
        "dropoffs": int(value(model.v[DEPOT_END])),
    }

    # Generate plot
    fig, ax = plot_rebalancing_map(
        plot_df=plot_df,
        network_gdf=network_df,
        journey_gdf=journey_gdf,
        depot_df=depot_df,
        depot_ops=depot_ops,
        zoom=ctx.plot_params["zoom"],
        title=f"Rebalancing Map - {ctx.target_date}",
        show=False,
    )

    # Save to file
    fig.savefig(ctx.results_dir / "rebalancing_map.jpg", dpi=300, bbox_inches="tight")
    plt.close(fig)

    logger.info("✓ Saved rebalancing_map.jpg")


def _save_results(
    model,
    result,
    stations_df: pd.DataFrame,
    network_df: gpd.GeoDataFrame,
    ctx: RunOptimizationContext,
) -> None:
    """
    Extract solution from model and save all output files.

    Args:
        model: Solved Pyomo model
        result: Solver result object
        stations_df: Station data DataFrame
        network_df: Network data GeoDataFrame
        ctx: RunOptimizationContext with paths and parameters
    """
    logger.info("=" * 60)
    logger.info("Saving optimization results")
    logger.info("=" * 60)

    _save_parameters(model, ctx)
    _save_metrics(model, result, ctx)
    _save_stations(model, ctx)
    _save_route(model, network_df, ctx)

    if ctx.plot_params["save_plot"]:
        _save_map(model, stations_df, network_df, ctx)

    logger.info(f"✓ All outputs saved to {ctx.results_dir}")


# ============================================================================
# Main public function
# ============================================================================


def run_optimization(ctx: RunOptimizationContext) -> None:
    """
    Run bike rebalancing optimization for target date.

    Args:
        ctx: RunOptimizationContext containing configuration and output paths
    """
    logger.info("Starting rebalancing optimization")
    logger.info(f"Target date: {ctx.target_date}")
    logger.info(f"Truck capacity: {ctx.model_params['truck_capacity']} bikes")
    logger.info(f"Buffer: {ctx.model_params['buffer']} bikes/docks")
    logger.info(f"Solver: {ctx.solver_params['factory']}")

    # Load and prepare data
    stations_df, network_df = _load_and_prepare_data(ctx)

    # Build optimization model
    model = _build_model(stations_df, network_df, ctx)

    # Solve model
    result = _solve_model(model, ctx)

    # Save results
    _save_results(model, result, stations_df, network_df, ctx)

    logger.info("=" * 60)
    logger.info("✓ Optimization completed")
