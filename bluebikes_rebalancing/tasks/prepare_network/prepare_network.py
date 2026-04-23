# tasks/prepare_network/prepare_network.py

import json
import logging

import geopandas as gpd
import osmnx as ox
import pandas as pd
from shapely.geometry import LineString

from .types import PrepareNetworkContext

logger = logging.getLogger(__name__)


# ============================================================================
# Helper functions
# ============================================================================


def _load_station_data(ctx: PrepareNetworkContext) -> pd.DataFrame:
    """
    Load station metadata and filter to stations of interest.

    Args:
        ctx: PrepareNetworkContext with paths and configuration

    Returns:
        DataFrame with station metadata (short_name, lat, lon, capacity)
    """
    logger.info("Loading station data")

    # Load stations of interest
    soi_path = ctx.raw_stations_dir / "stations_of_interest.json"
    with open(soi_path) as f:
        soi = json.load(f)
    logger.info(f"Loaded {len(soi)} stations of interest")

    # Load full station metadata
    df_stations = pd.read_csv(ctx.station_metadata_path)

    # Filter to stations of interest
    filt = df_stations["short_name"].isin(soi)
    df_soi = df_stations.loc[filt, :].sort_values(by="short_name").reset_index(drop=True)

    # Keep only relevant columns
    cols = ["short_name", "lat", "lon", "capacity"]
    df_soi = df_soi[cols]

    logger.info(f"✓ Loaded {len(df_soi)} stations")
    return df_soi


def _validate_stations_in_bbox(
    df_stations: pd.DataFrame,
    depot_lat_lon: tuple[float, float],
    bbox: tuple[float, float, float, float],
) -> None:
    """
    Validate that all stations and depot are within network bounding box.

    Args:
        df_stations: DataFrame with station coordinates
        depot_lat_lon: Depot (lat, lon)
        bbox: Bounding box (west, south, east, north)

    Raises:
        ValueError: If any station or depot is outside bbox
    """
    logger.info("Validating stations are within network bounding box")

    west, south, east, north = bbox

    # Check depot
    depot_lat, depot_lon = depot_lat_lon
    if not (south <= depot_lat <= north and west <= depot_lon <= east):
        raise ValueError(
            f"Depot ({depot_lat}, {depot_lon}) is outside network bbox "
            f"(W={west}, S={south}, E={east}, N={north})"
        )

    # Check all stations
    outside_stations = []
    for _, row in df_stations.iterrows():
        lat, lon = row["lat"], row["lon"]
        if not (south <= lat <= north and west <= lon <= east):
            outside_stations.append(row["short_name"])

    if outside_stations:
        raise ValueError(
            f"The following stations are outside network bbox: {outside_stations}\n"
            f"Bbox: (W={west}, S={south}, E={east}, N={north})\n"
            f"This will cause spurious routing results using nearest network points."
        )

    logger.info("✓ All stations and depot are within network bbox")


def _create_station_information(
    df_stations: pd.DataFrame, depot_lat_lon: tuple[float, float]
) -> pd.DataFrame:
    """
    Create station information table with integer indices and add depot entries.

    Args:
        df_stations: DataFrame with station metadata (short_name, lat, lon, capacity)
        depot_lat_lon: Depot (lat, lon)

    Returns:
        DataFrame with columns: idx, short_name, lat, lon, capacity
    """
    logger.info("Creating station information table")

    # Create depot entries (capacity will be NA)
    df_depot_start = pd.DataFrame(
        [
            {
                "short_name": "depot_start",
                "lat": depot_lat_lon[0],
                "lon": depot_lat_lon[1],
                "capacity": None,
            }
        ]
    )
    df_depot_end = pd.DataFrame(
        [
            {
                "short_name": "depot_end",
                "lat": depot_lat_lon[0],
                "lon": depot_lat_lon[1],
                "capacity": None,
            }
        ]
    )

    # Concatenate: depot_start, stations, depot_end
    df_station_info = pd.concat(
        [df_depot_start, df_stations[["short_name", "lat", "lon", "capacity"]], df_depot_end]
    ).reset_index(drop=True)

    # Create index column
    df_station_info.insert(0, "idx", range(len(df_station_info)))

    logger.info(
        f"✓ Created station information for {len(df_station_info)} entries (includes depot_start and depot_end)"
    )

    return df_station_info


def _download_osm_network(bbox: tuple[float, float, float, float]) -> object:
    """
    Download OSM network and adjust edge speeds.

    Args:
        bbox: Bounding box (west, south, east, north)

    Returns:
        OSMnx graph with adjusted speeds and travel times
    """
    logger.info("Downloading OSM network")
    logger.info(f"Bounding box (WSEN): {bbox}")

    # Download network
    network = ox.graph_from_bbox(bbox, network_type="drive", simplify=True, truncate_by_edge=True)
    logger.info("✓ Network downloaded")

    # Add edge speeds
    network = ox.add_edge_speeds(network)
    gdf_nodes, gdf_edges = ox.graph_to_gdfs(network)

    # Adjust speeds based on manual calibration
    logger.info("Adjusting edge speeds based on calibration")
    logger.warning(
        "Speed adjustments are calibrated for Boston (Fenway, Longwood, NEU, BU areas). "
        "If using network in different region, adjust speed calibration in prepare_network.py"
    )

    def change_speed(x):
        if x >= 50:
            return x * 0.85
        elif (x < 50) and (x > 42):
            return x * 0.65
        elif (x <= 50) and (x >= 35):
            return x * 0.55
        else:
            return x

    gdf_edges["speed_kph"] = gdf_edges["speed_kph"].apply(change_speed)

    # Reconstruct graph with adjusted speeds
    network = ox.graph_from_gdfs(gdf_nodes, gdf_edges)
    network = ox.add_edge_travel_times(network)

    logger.info("✓ Edge speeds adjusted and travel times computed")

    return network


def _validate_network_calculations(network: object) -> None:
    """
    Validate that travel time calculations are consistent.

    Args:
        network: OSMnx graph

    Note:
        Uses a random edge to verify travel_time = (length / speed) * 3600
    """
    logger.info("Validating network travel time calculations")

    # Get first edge for validation
    u, v = list(network.edges())[0]
    edge = network[u][v][0]

    length_km = edge["length"] / 1000
    speed_kph = edge["speed_kph"]
    travel_time_calc = length_km / speed_kph * 3600

    logger.info(f"Sample edge validation:")
    logger.info(f"  Length: {length_km:.4f} km")
    logger.info(f"  Speed: {speed_kph:.4f} kph")
    logger.info(f"  Travel time (calculated): {travel_time_calc:.4f} s")
    logger.info(f"  Travel time (stored):     {edge['travel_time']:.4f} s")

    logger.info("✓ Network calculations validated")


def _create_od_pairs(df_with_depot: pd.DataFrame) -> pd.DataFrame:
    """
    Create all origin-destination pairs from station list.

    Args:
        df_with_depot: DataFrame with stations and depot (with idx column)

    Returns:
        DataFrame with all OD pairs (excluding same-origin-destination)
    """
    logger.info("Creating origin-destination pairs")

    # Cross join to create all pairs
    df_od = (
        df_with_depot[["idx", "short_name", "lon", "lat"]]
        .rename(
            columns={
                "idx": "origin_idx",
                "short_name": "short_name_o",
                "lon": "lon_o",
                "lat": "lat_o",
            }
        )
        .merge(
            df_with_depot[["idx", "short_name", "lon", "lat"]].rename(
                columns={
                    "idx": "dest_idx",
                    "short_name": "short_name_d",
                    "lon": "lon_d",
                    "lat": "lat_d",
                }
            ),
            how="cross",
        )
    ).reset_index(drop=True)

    # Filter out same origin-destination
    filt = df_od["origin_idx"] != df_od["dest_idx"]
    df_od = df_od.loc[filt, :].reset_index(drop=True)

    logger.info(f"✓ Created {len(df_od)} OD pairs (excluding diagonal)")

    return df_od


def _compute_routes(df_od: pd.DataFrame, network: object) -> pd.DataFrame:
    """
    Compute shortest path routes for all OD pairs.

    Args:
        df_od: DataFrame with OD pairs
        network: OSMnx graph

    Returns:
        DataFrame with route column added (list of node IDs)
    """
    logger.info("=" * 60)
    logger.info("Computing shortest path routes")
    logger.info("=" * 60)

    routes = []
    gdf_nodes, _ = ox.graph_to_gdfs(network)

    for _, row in df_od.iterrows():
        # Find nearest network nodes
        orig_node = ox.nearest_nodes(network, row["lon_o"], row["lat_o"])
        dest_node = ox.nearest_nodes(network, row["lon_d"], row["lat_d"])

        # Compute shortest path
        try:
            route = ox.shortest_path(network, orig_node, dest_node, weight="travel_time")
            routes.append(route)
        except Exception as e:
            logger.warning(f"Route failed for {row['short_name_o']} -> {row['short_name_d']}: {e}")
            routes.append(None)

    df_od["route_ox"] = routes

    # Validate all routes computed
    n_missing = df_od["route_ox"].isna().sum()
    if n_missing > 0:
        logger.warning(f"⚠ {n_missing} routes could not be computed")
    else:
        logger.info("✓ All routes computed successfully")

    return df_od


def _extract_route_geometries(df_od: pd.DataFrame, network: object) -> gpd.GeoDataFrame:
    """
    Convert route node sequences to LineString geometries.

    Args:
        df_od: DataFrame with route_ox column
        network: OSMnx graph

    Returns:
        GeoDataFrame with geometry column
    """
    logger.info("Extracting route geometries")

    gdf_nodes, _ = ox.graph_to_gdfs(network)

    # Create mapping of node ID to point geometry
    dict_node_point = {idx: gdf_nodes.loc[idx, "geometry"] for idx in gdf_nodes.index}

    def route_to_geom(id_list):
        if len(id_list) == 1:
            # For single-node routes, create a zero-length LineString
            point = dict_node_point[id_list[0]]
            return LineString([point, point])
        return LineString([dict_node_point[i] for i in id_list])

    df_od["geometry"] = df_od["route_ox"].apply(lambda x: route_to_geom(x))

    gdf_od = gpd.GeoDataFrame(df_od, geometry="geometry", crs="EPSG:4326")

    logger.info("✓ Route geometries created")

    return gdf_od


def _calculate_distance_ttime(gdf_od: gpd.GeoDataFrame, network: object) -> gpd.GeoDataFrame:
    """
    Calculate distance and travel time for each route.

    Args:
        gdf_od: GeoDataFrame with routes
        network: OSMnx graph

    Returns:
        GeoDataFrame with dist_m and ttime_s columns added
    """
    logger.info("Calculating distance and travel time")

    def route_travel_time(route, graph):
        if len(route) == 1:
            return 0.0, 0.0
        travel_time = sum(graph[u][v][0]["travel_time"] for u, v in zip(route[:-1], route[1:]))
        length_m = sum(graph[u][v][0]["length"] for u, v in zip(route[:-1], route[1:]))
        return travel_time, length_m

    gdf_od[["ttime_s", "dist_m"]] = gdf_od["route_ox"].apply(
        lambda r: pd.Series(route_travel_time(r, network))
    )

    logger.info("✓ Distance and travel time calculated")

    return gdf_od


def _validate_distances(gdf_od: gpd.GeoDataFrame) -> None:
    """
    Validate distance calculations by comparing with geometry length.

    Args:
        gdf_od: GeoDataFrame with dist_m and geometry

    Warning:
        Uses NAD83 Massachusetts projection (EPSG:26986). Change if network is
        in a different region.
    """
    logger.info("Validating distance calculations")
    logger.warning(
        "Distance validation uses NAD83 Massachusetts projection (EPSG:26986). "
        "If using network outside Boston area, update projection in prepare_network.py"
    )

    # Project to NAD83 for accurate distance measurement
    gdf_od_nad83 = gdf_od.to_crs("EPSG:26986")
    gdf_od["distance_m_check"] = gdf_od_nad83.geometry.length

    gdf_od["length_diff_m"] = gdf_od["dist_m"] - gdf_od["distance_m_check"]

    # Log statistics
    stats = gdf_od[["dist_m", "distance_m_check", "length_diff_m"]].describe()
    logger.info("Distance validation statistics:")
    logger.info(f"\n{stats}")

    logger.info("✓ Distance validation complete")


def _save_outputs(
    gdf_od: gpd.GeoDataFrame, df_station_info: pd.DataFrame, ctx: PrepareNetworkContext
) -> None:
    """
    Save network outputs: distance/ttime CSV, routes shapefile, station information CSV, and routes JSON.

    Args:
        gdf_od: GeoDataFrame with all route data
        df_station_info: DataFrame with station information (idx, short_name, lat, lon, capacity)
        ctx: PrepareNetworkContext with output paths
    """
    logger.info("=" * 60)
    logger.info("Saving outputs")
    logger.info("=" * 60)

    # Save distance/travel time CSV (long format)
    cols_csv = ["origin_idx", "dest_idx", "dist_m", "ttime_s"]
    df_dist_ttime = gdf_od[cols_csv].copy()
    df_dist_ttime.to_csv(ctx.dist_ttime_path, index=False)
    logger.info(f"✓ Saved distance/travel time CSV: {ctx.dist_ttime_path}")

    # Save routes shapefile (geometry only, no route_ox)
    cols_shp = ["origin_idx", "dest_idx", "geometry"]
    gdf_routes = gdf_od[cols_shp].copy()
    gdf_routes.to_file(ctx.routes_shapefile_path)
    logger.info(f"✓ Saved routes shapefile: {ctx.routes_shapefile_path}")

    # Save route node sequences as JSON
    routes_dict = {
        f"{row['origin_idx']}_{row['dest_idx']}": row["route_ox"] for _, row in gdf_od.iterrows()
    }
    with open(ctx.routes_json_path, "w") as f:
        json.dump(routes_dict, f, indent=2)
    logger.info(f"✓ Saved route node sequences: {ctx.routes_json_path}")

    # Save station information CSV
    df_station_info.to_csv(ctx.station_info_path, index=False)
    logger.info(f"✓ Saved station information: {ctx.station_info_path}")


# ============================================================================
# Main public function
# ============================================================================


def prepare_network(ctx: PrepareNetworkContext) -> None:
    """
    Prepare network distance and travel time matrices for optimization.

    Args:
        ctx: PrepareNetworkContext containing configuration and output paths
    """
    logger.info("Starting network preparation")
    logger.info(f"Depot location: {ctx.depot_lat_lon}")
    logger.info(f"Network bbox: {ctx.network_bbox}")

    # Load station data
    df_stations = _load_station_data(ctx)

    # Validate stations are within bbox
    _validate_stations_in_bbox(df_stations, ctx.depot_lat_lon, ctx.network_bbox)

    # Create station information table
    df_station_info = _create_station_information(df_stations, ctx.depot_lat_lon)

    # Download OSM network
    network = _download_osm_network(ctx.network_bbox)

    # Validate network calculations
    _validate_network_calculations(network)

    # Create OD pairs (using df_station_info instead of df_with_depot)
    df_od = _create_od_pairs(df_station_info)

    # Compute shortest path routes
    df_od = _compute_routes(df_od, network)

    # Extract route geometries
    gdf_od = _extract_route_geometries(df_od, network)

    # Calculate distance and travel time
    gdf_od = _calculate_distance_ttime(gdf_od, network)

    # Validate distances
    _validate_distances(gdf_od)

    # Save outputs
    _save_outputs(gdf_od, df_station_info, ctx)

    logger.info("=" * 60)
    logger.info("✓ Network preparation completed")
