# bluebikes_rebalancing/model/build_model.py

from pyomo.environ import (
    Binary,
    ConcreteModel,
    Constraint,
    NonNegativeIntegers,
    NonNegativeReals,
    Objective,
    Param,
    Set,
    Var,
    minimize,
)

import bluebikes_rebalancing.model.constraints as const


def objective_rule(m):
    routing_cost = m.alpha * sum(m.dist[i, j] * m.x[i, j] for (i, j) in m.ARCS)
    service_penalty = m.beta * sum((m.b_final[i] - m.t[i]) ** 2 for i in m.STATIONS)
    return routing_cost + service_penalty


def build_vrp_model(
    nodes, stations, b, c, t, dist, ttime, Q, B, T_MAX, ALPHA, BETA, SERVICE_TIME, TIME_PER_BIKE
):
    """
    Build the Bluebikes overnight rebalancing MIQP model.

    Constructs a single-vehicle routing problem where a van departs from a depot,
    visits a subset of bike-share stations, performs pickups and dropoffs, and
    returns to the depot. The objective minimizes total distance traveled weighted
    by ALPHA plus the squared deviation of final station inventories from target
    levels weighted by BETA.

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
        Vehicle capacity in bikes.
    B : int
        Buffer parameter: minimum bikes and minimum free docks required at each
        station after rebalancing.
    T_MAX : float
        Maximum operation time in minutes (typically 180 for a 3-hour window).
    ALPHA : float
        Weight on the routing cost term (distance in meters).
    BETA : float
        Weight on the service quality penalty term (squared bike deviations).
    SERVICE_TIME : float
        Fixed time in minutes charged per station visit.
    TIME_PER_BIKE : float
        Variable time in minutes per bike loaded or unloaded.

    Returns
    -------
    model : pyomo.environ.ConcreteModel
        Fully constructed and constrained Pyomo model, ready to be passed to a solver.
    """
    N = len(stations)
    M_low = {i: Q + b[i] for i in nodes}
    M_up = {i: Q + (c[i] - b[i]) for i in nodes}

    # --- Model ---
    model = ConcreteModel(name="Bluebikes_VRP")

    # --- Sets ---
    model.NODES = Set(initialize=nodes)
    model.STATIONS = Set(initialize=stations)
    model.ARCS = Set(initialize=dist.keys())

    # --- Parameters ---
    model.Q = Param(initialize=Q)
    model.B = Param(initialize=B)
    model.T = Param(initialize=T_MAX)
    model.alpha = Param(initialize=ALPHA)
    model.beta = Param(initialize=BETA)
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
    model.x = Var(model.ARCS, domain=Binary)
    model.u = Var(model.NODES, domain=NonNegativeIntegers, bounds=(0, None))
    model.v = Var(model.NODES, domain=NonNegativeIntegers, bounds=(0, None))
    model.y = Var(model.STATIONS, domain=Binary)
    model.b_final = Var(model.NODES, domain=NonNegativeIntegers, bounds=(0, None))
    model.w = Var(model.NODES, domain=NonNegativeIntegers, bounds=(0, Q))
    model.p = Var(model.STATIONS, domain=NonNegativeReals, bounds=(1, N))

    for i in model.NODES:
        model.u[i].setub(b[i])
        model.v[i].setub(c[i] - b[i])
        model.b_final[i].setub(c[i])

    # --- Objective ---
    model.obj = Objective(rule=objective_rule, sense=minimize)

    # --- Constraints ---
    # Route Structure
    model.leave_depot = Constraint(rule=const.leave_depot_rule)
    model.enter_depot = Constraint(rule=const.enter_depot_rule)
    model.no_return_start = Constraint(model.ARCS, rule=const.no_return_start_rule)
    model.no_depart_end = Constraint(model.ARCS, rule=const.no_depart_end_rule)
    model.flow_conservation = Constraint(model.STATIONS, rule=const.flow_conservation_rule)
    model.visit_once = Constraint(model.STATIONS, rule=const.visit_once_rule)

    # MTZ Subtour Elimination
    model.mtz = Constraint(model.ARCS, rule=const.mtz_rule)

    # Inventory Balance
    model.inventory_balance = Constraint(model.NODES, rule=const.inventory_balance_rule)

    # Vehicle Load Tracking
    model.load_lower = Constraint(model.ARCS, rule=const.load_lower_rule)
    model.load_upper = Constraint(model.ARCS, rule=const.load_upper_rule)
    model.initial_load = Constraint(rule=const.initial_load_rule)
    model.final_load = Constraint(rule=const.final_load_rule)

    # Operational Bounds
    model.buffer_lower = Constraint(model.STATIONS, rule=const.buffer_lower_rule)
    model.buffer_upper = Constraint(model.STATIONS, rule=const.buffer_upper_rule)
    model.pickup_visit = Constraint(model.NODES, rule=const.pickup_visit_rule)
    model.delivery_visit = Constraint(model.NODES, rule=const.delivery_visit_rule)
    model.pickup_direction = Constraint(model.STATIONS, rule=const.pickup_direction_rule)
    model.delivery_direction = Constraint(model.STATIONS, rule=const.delivery_direction_rule)

    # Time Budget
    model.time_budget = Constraint(rule=const.time_budget_rule)

    return model
