import random as rnd

import contextily as ctx
import geopandas as gpd
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
import matplotlib.pyplot as plt
import numpy as np
from pyproj import Transformer
from shapely.geometry import Point

COLORS = [
    "#f1b6da",
    "#c51b7d",
    "#fdae61",
    "#d73027",
    "#a6d96a",
    "#1a9850",
    "#abd9e9",
    "#2166ac",
    "#b2abd2",
    "#542788",
    "#bababa",
    "#4d4d4d",
]

# Per-vehicle palette for the multi-vehicle map. COLORS is arranged in
# (lighter, darker) hue pairs; the saturated odd indexes (all at the same
# lightness) draw the route lines, and each route's bike-count label boxes use
# the paired lighter even index. The last two COLORS entries are grays reserved
# for the depot, so the fleet palette holds 5 vehicles before it wraps.
VEHICLE_ROUTE_COLORS = COLORS[1:10:2]  # indexes 1, 3, 5, 7, 9
VEHICLE_BOX_COLORS = COLORS[0:9:2]  # indexes 0, 2, 4, 6, 8


def plot_daily_longterm(
    df_daily,
    columns_to_plot,
    title="",
    xlabel="",
    ylabel="",
    color_list=None,
    linestyle_list=None,
    legend_labels=None,
    figsize=(12, 6),
    ylim_max=None,
    show=True,
):
    """
    Plot daily/long-term time series profile.

    Parameters:
    -----------
    df_daily : pd.DataFrame
        DataFrame indexed by date/timestamp with columns to plot
    columns_to_plot : list
        List of column names to plot
    title : str, optional
        Plot title
    xlabel : str, optional
        X-axis label
    ylabel : str, optional
        Y-axis label
    color_list : list, optional
        Colors for each column (default: uses first N from colors)
    linestyle_list : list, optional
        Line styles for each column (default: '-' for all)
    legend_labels : list, optional
        Legend labels for each column (default: column names)
    figsize : tuple, optional
        Figure size (width, height)
    ylim_max : float, optional
        Maximum y-axis limit (default: None, auto-scales)
    """
    # Set defaults
    if color_list is None:
        color_list = COLORS[: len(columns_to_plot)]
    if linestyle_list is None:
        linestyle_list = ["-"] * len(columns_to_plot)
    if legend_labels is None:
        legend_labels = columns_to_plot

    plt.figure(figsize=figsize)

    # Plot each column
    for col, color, linestyle, label in zip(
        columns_to_plot, color_list, linestyle_list, legend_labels
    ):
        plt.plot(
            df_daily.index,
            df_daily[col],
            color=color,
            linewidth=1,
            linestyle=linestyle,
            label=label,
            alpha=0.8,
            marker="o",
            markersize=1.05,
        )

    if title:
        plt.title(title, fontsize=15)
    if xlabel:
        plt.xlabel(xlabel, fontsize=11)
    if ylabel:
        plt.ylabel(ylabel, fontsize=11)

    # Set y-axis limit if specified
    if ylim_max is not None:
        ax = plt.gca()
        ax.set_ylim(top=ylim_max)

    plt.legend(loc="best", fontsize=10)
    plt.grid(True, alpha=0.3)

    # Reduce number of ticks
    ax = plt.gca()
    ax.xaxis.set_major_locator(plt.MaxNLocator(nbins=8))
    ax.yaxis.set_major_locator(plt.MaxNLocator(nbins=6))

    plt.tight_layout()

    if show:
        plt.show()


def plot_points_on_map(
    df_points,
    lat_col="lat",
    lon_col="lon",
    label_col=None,
    group_col=None,
    group_values=None,
    color_list=None,
    marker_list=None,
    markersize_list=None,
    legend_labels=None,
    figsize=(12, 12),
    bbox=None,
    show_labels=True,
    title="Points on Map",
    zoom=12,
):
    """
    Plot points on map with flexible grouping and styling.

    Parameters:
    -----------
    df_points : pd.DataFrame
        DataFrame with point data
    lat_col : str
        Column name for latitude (default: 'lat')
    lon_col : str
        Column name for longitude (default: 'lon')
    label_col : str, optional
        Column name for point labels (default: None)
    group_col : str, optional
        Column name to group points by (default: None, all same group)
    group_values : list of lists
        List of value lists defining each group.
        Example: [['A', 'B'], ['C', 'D'], ['E']] creates 3 groups
        Must match length of color_list
    color_list : list
        Colors for each group. Must match length of group_values
    marker_list : list or str, optional
        Marker types. If single value, applies to all groups (default: 'o')
    markersize_list : list or int, optional
        Marker sizes. If single value, applies to all groups (default: 50)
    legend_labels : list, optional
        Custom labels for legend (default: 'Group 1', 'Group 2', etc.)
    figsize : tuple
        Figure size (width, height)
    bbox : tuple, optional
        Bounding box (min_lon, min_lat, max_lon, max_lat)
    show_labels : bool
        Whether to show point labels (only if <= 20 points)
    title : str
        Plot title
    zoom : int
        Basemap zoom level
    """
    df_plot = df_points.copy()

    # Filter by bounding box if provided
    if bbox is not None:
        min_lon, min_lat, max_lon, max_lat = bbox
        df_plot = df_plot[
            (df_plot[lon_col] >= min_lon)
            & (df_plot[lon_col] <= max_lon)
            & (df_plot[lat_col] >= min_lat)
            & (df_plot[lat_col] <= max_lat)
        ]

    # Handle grouping
    if group_col is None or group_values is None:
        # Single group - all points
        df_plot["_group"] = 0
        n_groups = 1
        if color_list is None:
            color_list = [COLORS[2]]
    else:
        # Assign groups based on group_values
        n_groups = len(group_values)
        df_plot["_group"] = -1  # Unassigned points get -1

        for group_idx, values in enumerate(group_values):
            mask = df_plot[group_col].isin(values)
            df_plot.loc[mask, "_group"] = group_idx

        # Filter out unassigned points
        df_plot = df_plot[df_plot["_group"] != -1]

        # Validate color_list matches group_values
        if color_list is None or len(color_list) != n_groups:
            raise ValueError(f"color_list must have {n_groups} colors to match group_values")

    # Handle markers - replicate if single value
    if marker_list is None:
        marker_list = ["o"] * n_groups
    elif isinstance(marker_list, str):
        marker_list = [marker_list] * n_groups
    elif len(marker_list) == 1:
        marker_list = marker_list * n_groups
    elif len(marker_list) != n_groups:
        raise ValueError(f"marker_list must have {n_groups} values or be a single value")

    # Handle marker sizes - replicate if single value
    if markersize_list is None:
        markersize_list = [50] * n_groups
    elif isinstance(markersize_list, (int, float)):
        markersize_list = [markersize_list] * n_groups
    elif len(markersize_list) == 1:
        markersize_list = markersize_list * n_groups
    elif len(markersize_list) != n_groups:
        raise ValueError(f"markersize_list must have {n_groups} values or be a single value")

    # Handle legend labels
    if legend_labels is None:
        legend_labels = [f"Group {i+1}" for i in range(n_groups)]
    elif len(legend_labels) != n_groups:
        raise ValueError(f"legend_labels must have {n_groups} labels")

    # Create GeoDataFrame
    geometry = [Point(xy) for xy in zip(df_plot[lon_col], df_plot[lat_col])]
    gdf = gpd.GeoDataFrame(df_plot, geometry=geometry, crs="EPSG:4326")
    gdf = gdf.to_crs(epsg=3857)

    # Create plot
    fig, ax = plt.subplots(figsize=figsize)

    # Plot each group
    for group_idx in range(n_groups):
        group_gdf = gdf[gdf["_group"] == group_idx]
        if len(group_gdf) > 0:
            group_gdf.plot(
                ax=ax,
                color=color_list[group_idx],
                marker=marker_list[group_idx],
                markersize=markersize_list[group_idx],
                alpha=0.7,
                edgecolor="black",
                linewidth=0.5,
                zorder=5,
                label=legend_labels[group_idx],
            )

    # Set map extent if bbox provided
    if bbox is not None:
        transformer = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
        min_x, min_y = transformer.transform(min_lon, min_lat)
        max_x, max_y = transformer.transform(max_lon, max_lat)
        ax.set_xlim(min_x, max_x)
        ax.set_ylim(min_y, max_y)

    # Add basemap
    ctx.add_basemap(ax, source=ctx.providers.CartoDB.Positron, zoom=zoom)

    # Labels
    if show_labels and label_col is not None and len(df_plot) <= 20:
        for idx, row in gdf.iterrows():
            ax.annotate(
                row[label_col],
                xy=(row.geometry.x, row.geometry.y),
                xytext=(5, 5),
                textcoords="offset points",
                fontsize=8,
                alpha=0.8,
                bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8),
                zorder=6,
            )

    ax.set_title(title, fontsize=15)
    if n_groups > 1:
        ax.legend(loc="upper right", fontsize=10)
    ax.axis("off")
    plt.tight_layout()
    plt.show()

    return fig, ax


def plot_rebalancing_map(
    plot_df,
    network_gdf,
    journey_gdf,
    depot_df,
    depot_ops,
    figsize=(12, 12),
    zoom=13,
    title="Fleet rebalancing journeys and initial station inventory deviation",
    vehicle_colors=None,
    depot_color=COLORS[-1],
    show=True,
):
    """
    Plot the multi-vehicle fleet rebalancing journeys on a map with station
    inventory deviations.

    Each vehicle's route is drawn in a distinct color, with per-vehicle visit
    sequence numbers. Stations are colored by their initial deviation from
    target, and the shared depot reports the fleet's aggregate load/return.

    Parameters
    ----------
    plot_df : pd.DataFrame
        Station-level dataframe with columns: station, lat, lon, deviation,
        pickups, dropoffs. Must include only stations (no depots). pickups and
        dropoffs are summed over the fleet.
    network_gdf : gpd.GeoDataFrame
        Full road network GeoDataFrame (background layer).
    journey_gdf : gpd.GeoDataFrame
        Arcs traveled by the fleet, ordered per vehicle, with a 'vehicle' column
        identifying which vehicle traversed each arc (plus 'from' and 'to').
    depot_df : pd.DataFrame
        Single-row dataframe with columns lat, lon for the depot location.
    depot_ops : list of dict
        Per-vehicle depot operations, one dict per vehicle that touches the
        depot: {'vehicle': k, 'pickups': bikes loaded at depot_start,
        'dropoffs': bikes returned at depot_end}. Rendered as a vertical stack
        of route-colored boxes (white text) so the shared depot location does
        not overlap.
    figsize : tuple
        Figure size (width, height).
    zoom : int
        Basemap tile zoom level.
    title : str
        Plot title.
    vehicle_colors : dict, optional
        Mapping {vehicle: route line color}. If None, each vehicle gets a
        saturated odd-index COLORS entry for its route, paired with the lighter
        even-index entry behind its bike-count labels (up to 5 vehicles).
    depot_color : str
        Color for the depot marker.
    show : bool
        If True, display the plot. If False, return figure without showing.

    Returns
    -------
    fig, ax : matplotlib Figure and Axes
    """
    fig, ax = plt.subplots(figsize=figsize)

    # Road network background
    network_gdf.to_crs(epsg=3857).plot(
        ax=ax, color="lightgray", linewidth=0.3, alpha=0.5, zorder=1
    )

    # Determine which vehicles are present in the solution
    vehicles = []
    if len(journey_gdf) > 0 and "vehicle" in journey_gdf.columns:
        vehicles = sorted(journey_gdf["vehicle"].unique())

    # Assign colors per vehicle: a saturated odd-index route line paired with
    # the lighter even-index color drawn behind that vehicle's bike-count
    # labels. The palette holds 5 vehicles before wrapping.
    if vehicle_colors is None:
        vehicle_colors = {
            veh: VEHICLE_ROUTE_COLORS[idx % len(VEHICLE_ROUTE_COLORS)]
            for idx, veh in enumerate(vehicles)
        }
    vehicle_box_colors = {
        veh: VEHICLE_BOX_COLORS[idx % len(VEHICLE_BOX_COLORS)]
        for idx, veh in enumerate(vehicles)
    }

    # Plot each vehicle's journey and build per-vehicle visit sequence mapping
    # station -> (vehicle, sequence_number)
    station_sequence = {}
    for veh in vehicles:
        veh_gdf = journey_gdf[journey_gdf["vehicle"] == veh]
        if len(veh_gdf) == 0:
            continue
        veh_gdf.to_crs(epsg=3857).plot(
            ax=ax, color=vehicle_colors[veh], linewidth=2.5, alpha=0.9, zorder=2
        )
        for seq, dest_station in enumerate(veh_gdf["to"].tolist(), 1):
            if dest_station not in station_sequence:
                station_sequence[dest_station] = (veh, seq)

    # Stations colored by deviation
    gdf_stations = gpd.GeoDataFrame(
        plot_df,
        geometry=[Point(row.lon, row.lat) for _, row in plot_df.iterrows()],
        crs="EPSG:4326",
    ).to_crs(epsg=3857)

    dev_abs_max = plot_df["deviation"].abs().max()
    scatter = ax.scatter(
        gdf_stations.geometry.x,
        gdf_stations.geometry.y,
        c=plot_df["deviation"],
        cmap="RdBu_r",
        vmin=-dev_abs_max,
        vmax=dev_abs_max,
        s=80,
        edgecolor="black",
        linewidth=0.5,
        zorder=5,
        alpha=0.9,
    )

    # Visited stations: ring + per-vehicle sequence number + net operation label
    visited_stations = set(
        plot_df.loc[(plot_df["pickups"] > 0) | (plot_df["dropoffs"] > 0), "station"]
    )

    for _, row in gdf_stations.iterrows():
        if row["station"] not in visited_stations:
            continue

        ax.scatter(
            row.geometry.x,
            row.geometry.y,
            s=150,
            facecolor="none",
            edgecolor="black",
            linewidth=1.5,
            zorder=6,
        )

        # Sequence number (route color) and net-bikes box (paired lighter
        # color), both keyed to the vehicle that serves this station
        seq_info = station_sequence.get(row["station"])
        box_color = "white"
        if seq_info is not None:
            veh, seq = seq_info
            box_color = vehicle_box_colors.get(veh, "white")
            ax.annotate(
                str(seq),
                xy=(row.geometry.x, row.geometry.y),
                xytext=(0, 10),
                textcoords="offset points",
                fontsize=7,
                fontweight="bold",
                color=vehicle_colors.get(veh, "black"),
                ha="center",
                va="center",
                zorder=6.5,
            )

        net = int(row["dropoffs"]) - int(row["pickups"])
        label = f"+{net}" if net > 0 else str(net)
        ax.annotate(
            label,
            xy=(row.geometry.x, row.geometry.y),
            xytext=(8, 6),
            textcoords="offset points",
            fontsize=7,
            fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.2", facecolor=box_color, alpha=0.85),
            zorder=7,
        )

    # Depot marker
    depot_gdf = gpd.GeoDataFrame(
        depot_df,
        geometry=[Point(depot_df.iloc[0].lon, depot_df.iloc[0].lat)],
        crs="EPSG:4326",
    ).to_crs(epsg=3857)
    depot_x = depot_gdf.geometry.x.iloc[0]
    depot_y = depot_gdf.geometry.y.iloc[0]

    ax.scatter(
        depot_x,
        depot_y,
        s=80,
        color=depot_color,
        edgecolor="black",
        linewidth=0.5,
        zorder=8,
        label="Depot",
    )

    # Per-vehicle depot operation labels. All vehicles share the depot location,
    # so the boxes are stacked vertically (centered on the marker) to avoid
    # overlap. Each box is filled with that vehicle's route color and shows its
    # depot load (−, bikes taken onto the van) and/or return (+, bikes brought
    # back), in white.
    depot_entries = [
        e for e in depot_ops if e.get("pickups", 0) > 0 or e.get("dropoffs", 0) > 0
    ]
    row_step = 15  # points between stacked boxes
    y_top = (len(depot_entries) - 1) / 2 * row_step  # center the stack on the depot
    for idx, entry in enumerate(depot_entries):
        load = entry.get("pickups", 0)
        ret = entry.get("dropoffs", 0)
        parts = []
        if load > 0:
            parts.append(f"-{load}")
        if ret > 0:
            parts.append(f"+{ret}")

        ax.annotate(
            " ".join(parts),
            xy=(depot_x, depot_y),
            xytext=(-10, y_top - idx * row_step),
            textcoords="offset points",
            fontsize=7,
            fontweight="bold",
            color="white",
            bbox=dict(
                boxstyle="round,pad=0.2",
                facecolor=vehicle_colors.get(entry["vehicle"], depot_color),
                edgecolor="black",
                linewidth=0.4,
                alpha=0.95,
            ),
            zorder=8.5,
            ha="right",
            va="center",
        )

    cbar = plt.colorbar(scatter, ax=ax, shrink=0.25)
    cbar.set_label("Initial deviation (inventory - target)", rotation=90, labelpad=10)
    cbar.ax.yaxis.set_label_position("left")
    cbar.ax.tick_params(labelsize=8)

    ctx.add_basemap(ax, source=ctx.providers.CartoDB.Positron, zoom=zoom)

    # Custom legend: one line per vehicle, plus depot and operation markers
    legend_elements = [
        Line2D([0], [0], color=vehicle_colors[veh], linewidth=2.5, label=f"Vehicle {veh}")
        for veh in vehicles
    ]
    legend_elements += [
        Line2D(
            [0],
            [0],
            marker="o",
            color="w",
            markerfacecolor=depot_color,
            markersize=8,
            markeredgecolor="black",
            markeredgewidth=0.5,
            label="Depot",
        ),
        Line2D(
            [0],
            [0],
            marker="s",
            color="w",
            markerfacecolor="white",
            markersize=8,
            markeredgecolor="black",
            label="Dropoffs (+) / Pickups (−) at station",
            linestyle="None",
        ),
        Line2D(
            [0],
            [0],
            marker="s",
            color="w",
            markerfacecolor="black",
            markersize=8,
            markeredgecolor="black",
            label="Dropoffs (+) / Pickups (−) at depot",
            linestyle="None",
        ),
    ]

    ax.legend(handles=legend_elements, loc="best", fontsize=9)

    ax.set_title(title, fontsize=14)

    ax.axis("off")
    plt.tight_layout()
    if show:
        plt.show()

    return fig, ax
