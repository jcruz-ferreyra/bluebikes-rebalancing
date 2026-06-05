# bluebikes_rebalancing/model/build_model.py

from pyomo.environ import (
    Binary,
    ConcreteModel,
    Constraint,
    NonNegativeIntegers,
    NonNegativeReals,
    Objective,
    Param,
    RangeSet,
    Set,
    Var,
    minimize,
)

import bluebikes_rebalancing.model.constraints as const


def objective_rule(m):
    routing_cost = m.alpha * sum(
        m.dist[i, j] * m.x[i, j, k] for (i, j) in m.ARCS for k in m.VEHICLES
    )
    service_penalty = m.beta * sum((m.b_final[i] - m.t[i]) ** 2 for i in m.STATIONS)
    # Fixed cost per deployed vehicle. The station departures from the start
    # depot, summed over vehicles, count the vehicles used (j != depot_end is the
    # "used" indicator, consistent with no_depot_to_depot).
    deployment_cost = m.gamma * sum(
        m.x[i, j, k]
        for (i, j) in m.ARCS
        if i == const.DEPOT_START and j != const.DEPOT_END
        for k in m.VEHICLES
    )
    return routing_cost + service_penalty + deployment_cost


def build_vrp_model(
    nodes,
    stations,
    b,
    c,
    t,
    dist,
    ttime,
    Q,
    K,
    S,
    B,
    T_MAX,
    ALPHA,
    BETA,
    GAMMA,
    SERVICE_TIME,
    TIME_PER_BIKE,
):
    """
    Build the Bluebikes overnight rebalancing MIQP model (multi-vehicle fleet).

    Constructs a multi-vehicle routing problem where a fleet of up to K identical
    vans departs from a shared depot, each visits a subset of bike-share stations,
    performs pickups and dropoffs, and returns to the depot. Every station is
    served by at most one vehicle. The objective minimizes total distance traveled
    over the whole fleet weighted by ALPHA plus the squared deviation of final
    station inventories from target levels weighted by BETA.

    Parameters
    ----------
    nodes : list of str
        All nodes in the problem, including depot_start, stations, and depot_end.
    stations : list of str
        Station nodes only (excludes depots).
    b : dict {str: int}
        Initial bike inventory at each node. Depot start is set to Q, depot end to 0.
    c : dict {str: int}
        Docking capacity at each node. Both depots are set to Q.
    t : dict {str: float}
        Target inventory at each station after rebalancing, defined as c[i]/2 - d[i]
        where d[i] = dropoffs_forecast - pickups_forecast.
    dist : dict {(str, str): float}
        Pairwise distances in meters between nodes, keyed by (origin, destination).
    ttime : dict {(str, str): float}
        Pairwise travel times in minutes between nodes, keyed by (origin, destination).
    Q : int
        Per-vehicle capacity in bikes.
    K : int
        Fleet size: the maximum number of vehicles that may be used. A vehicle may
        stay unused.
    S : int
        Total depot capacity: the bikes the fleet can collectively source at the
        start and return at the end. Set S = Q to preserve the single-vehicle
        assumption.
    B : int
        Buffer parameter: minimum bikes and minimum free docks required at each
        station after rebalancing.
    T_MAX : float
        Maximum operation time in minutes per vehicle (typically 180 for a 3-hour
        window).
    ALPHA : float
        Weight on the routing cost term (distance in meters).
    BETA : float
        Weight on the service quality penalty term (squared bike deviations).
    GAMMA : float
        Fixed deployment cost charged once per vehicle that leaves the depot, in
        the same units as the routing and penalty terms. Makes fleet size
        endogenous: a vehicle is used only when its benefit exceeds GAMMA.
    SERVICE_TIME : float
        Fixed time in minutes charged per station visit.
    TIME_PER_BIKE : float
        Variable time in minutes per bike loaded or unloaded.

    Returns
    -------
    model : pyomo.environ.ConcreteModel
        Fully constructed and constrained Pyomo model, ready to be passed to a solver.
    """
    # Guard: initial inventory must not exceed capacity. Otherwise the dropoff
    # bound v[i, k] <= c[i] - b[i] goes negative on a nonnegative variable and
    # the model is infeasible with an opaque solver message.
    over_capacity = [i for i in nodes if b[i] > c[i]]
    if over_capacity:
        details = ", ".join(f"{i} (b={b[i]}, c={c[i]})" for i in over_capacity)
        raise ValueError(f"Initial inventory exceeds capacity at: {details}")

    N = len(stations)
    M_low = {i: Q + b[i] for i in nodes}
    M_up = {i: Q + (c[i] - b[i]) for i in nodes}

    # --- Model ---
    model = ConcreteModel(name="Bluebikes_VRP_Fleet")

    # --- Sets ---
    model.NODES = Set(initialize=nodes)
    model.STATIONS = Set(initialize=stations)
    model.ARCS = Set(initialize=dist.keys())
    model.VEHICLES = RangeSet(1, K)

    # --- Parameters ---
    model.Q = Param(initialize=Q)
    model.K = Param(initialize=K)
    model.S = Param(initialize=S)
    model.B = Param(initialize=B)
    model.T = Param(initialize=T_MAX)
    model.alpha = Param(initialize=ALPHA)
    model.beta = Param(initialize=BETA)
    model.gamma = Param(initialize=GAMMA)
    model.s = Param(initialize=SERVICE_TIME)
    model.tau = Param(initialize=TIME_PER_BIKE)
    model.M_low = Param(model.NODES, initialize=M_low)
    model.M_up = Param(model.NODES, initialize=M_up)
    model.b = Param(model.NODES, initialize=b)
    model.c = Param(model.NODES, initialize=c)
    model.t = Param(model.STATIONS, initialize=t)
    model.dist = Param(model.ARCS, initialize=dist)
    model.ttime = Param(model.ARCS, initialize=ttime)

    # --- Variables ---
    model.x = Var(model.ARCS, model.VEHICLES, domain=Binary)
    model.u = Var(model.NODES, model.VEHICLES, domain=NonNegativeIntegers, bounds=(0, None))
    model.v = Var(model.NODES, model.VEHICLES, domain=NonNegativeIntegers, bounds=(0, None))
    model.y = Var(model.STATIONS, domain=Binary)
    model.b_final = Var(model.STATIONS, domain=NonNegativeIntegers, bounds=(0, None))
    model.w = Var(model.NODES, model.VEHICLES, domain=NonNegativeIntegers, bounds=(0, Q))
    model.p = Var(model.STATIONS, domain=NonNegativeReals, bounds=(1, N))

    for k in model.VEHICLES:
        for i in model.NODES:
            model.u[i, k].setub(b[i])
            model.v[i, k].setub(c[i] - b[i])
    for i in model.STATIONS:
        model.b_final[i].setub(c[i])

    # --- Objective ---
    model.obj = Objective(rule=objective_rule, sense=minimize)

    # --- Constraints ---
    # Route Structure (per vehicle)
    model.leave_depot = Constraint(model.VEHICLES, rule=const.leave_depot_rule)
    model.enter_depot = Constraint(model.VEHICLES, rule=const.enter_depot_rule)
    model.depot_consistency = Constraint(model.VEHICLES, rule=const.depot_consistency_rule)
    model.no_return_start = Constraint(model.ARCS, model.VEHICLES, rule=const.no_return_start_rule)
    model.no_depart_end = Constraint(model.ARCS, model.VEHICLES, rule=const.no_depart_end_rule)
    model.no_depot_to_depot = Constraint(model.VEHICLES, rule=const.no_depot_to_depot_rule)
    model.flow_conservation = Constraint(
        model.STATIONS, model.VEHICLES, rule=const.flow_conservation_rule
    )

    # Station Assignment (fleet wide)
    model.visit_once = Constraint(model.STATIONS, rule=const.visit_once_rule)

    # MTZ Subtour Elimination (fleet wide)
    model.mtz = Constraint(model.ARCS, rule=const.mtz_rule)

    # Inventory Balance (stations only)
    model.inventory_balance = Constraint(model.STATIONS, rule=const.inventory_balance_rule)

    # Vehicle Load Tracking (per vehicle)
    model.load_lower = Constraint(model.ARCS, model.VEHICLES, rule=const.load_lower_rule)
    model.load_upper = Constraint(model.ARCS, model.VEHICLES, rule=const.load_upper_rule)
    model.initial_load = Constraint(model.VEHICLES, rule=const.initial_load_rule)
    model.final_load = Constraint(model.VEHICLES, rule=const.final_load_rule)

    # Operational Bounds
    model.buffer_lower = Constraint(model.STATIONS, rule=const.buffer_lower_rule)
    model.buffer_upper = Constraint(model.STATIONS, rule=const.buffer_upper_rule)
    model.pickup_visit = Constraint(model.NODES, model.VEHICLES, rule=const.pickup_visit_rule)
    model.delivery_visit = Constraint(model.NODES, model.VEHICLES, rule=const.delivery_visit_rule)
    model.depot_source_capacity = Constraint(rule=const.depot_source_capacity_rule)
    model.depot_sink_capacity = Constraint(rule=const.depot_sink_capacity_rule)
    model.pickup_direction = Constraint(
        model.STATIONS, model.VEHICLES, rule=const.pickup_direction_rule
    )
    model.delivery_direction = Constraint(
        model.STATIONS, model.VEHICLES, rule=const.delivery_direction_rule
    )

    # Time Budget (per vehicle)
    model.time_budget = Constraint(model.VEHICLES, rule=const.time_budget_rule)

    # Symmetry Breaking
    model.symmetry_break = Constraint(model.VEHICLES, rule=const.symmetry_break_rule)

    return model
