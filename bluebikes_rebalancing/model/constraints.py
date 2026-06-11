# bluebikes_rebalancing/model/constraints.py
#
# Multi-vehicle (fleet) rebalancing constraints, based on references/math_model.md.
# Routing and bike-operation variables carry a vehicle index k; station-level
# variables (b_final, y, p) remain fleet-wide because a station is served by at
# most one vehicle.

from pyomo.environ import Constraint

DEPOT_START = "depot_start"
DEPOT_END = "depot_end"


# --- Route Structure (per vehicle) ---
def leave_depot_rule(m, k):
    """Each vehicle leaves the start depot at most once."""
    return sum(m.x[i, j, k] for (i, j) in m.ARCS if i == DEPOT_START) <= 1


def enter_depot_rule(m, k):
    """Each vehicle enters the end depot at most once."""
    return sum(m.x[i, j, k] for (i, j) in m.ARCS if j == DEPOT_END) <= 1


def depot_consistency_rule(m, k):
    """A vehicle leaves the start depot iff it returns to the end depot.

    Logically redundant: summing per-vehicle flow conservation over all nodes
    (stations cancel, no_return_start zeroes start-depot inflow, no_depart_end
    zeroes end-depot outflow) already forces leave_k == enter_k. Kept as explicit
    self-documentation; it adds only K rows and no feasible-region restriction."""
    leave = sum(m.x[i, j, k] for (i, j) in m.ARCS if i == DEPOT_START)
    enter = sum(m.x[i, j, k] for (i, j) in m.ARCS if j == DEPOT_END)
    return leave == enter


def no_return_start_rule(m, i, j, k):
    """No vehicle may travel back into the start depot."""
    if j == DEPOT_START:
        return m.x[i, j, k] == 0
    return Constraint.Skip


def no_depart_end_rule(m, i, j, k):
    """No vehicle may depart from the end depot."""
    if i == DEPOT_END:
        return m.x[i, j, k] == 0
    return Constraint.Skip


def no_depot_to_depot_rule(m, k):
    """Forbid the degenerate empty route that travels straight from the start
    depot to the end depot without serving any station. Such an arc costs zero
    distance (both depots share a location), so it would otherwise let an unused
    vehicle register as 'used' and undermine symmetry breaking."""
    if (DEPOT_START, DEPOT_END) in m.ARCS:
        return m.x[DEPOT_START, DEPOT_END, k] == 0
    return Constraint.Skip


def flow_conservation_rule(m, h, k):
    """For each station and vehicle, inflow equals outflow."""
    inflow = sum(m.x[i, j, k] for (i, j) in m.ARCS if j == h)
    outflow = sum(m.x[i, j, k] for (i, j) in m.ARCS if i == h)
    return inflow == outflow


# --- Station Assignment (fleet wide) ---
def visit_once_rule(m, h):
    """Each station is served by at most one vehicle, at most once."""
    return sum(m.x[i, j, k] for (i, j) in m.ARCS if j == h for k in m.VEHICLES) <= 1


# --- MTZ Subtour Elimination (fleet wide) ---
def mtz_rule(m, i, j):
    N = len(m.STATIONS)
    if i in m.STATIONS and j in m.STATIONS:
        # lifted MTZ (Desrochers and Laporte): the reverse arc term forces
        # consecutive positions on used arcs and forbids loops between two
        # stations, tightening the LP relaxation without removing any route
        x_forward = sum(m.x[i, j, k] for k in m.VEHICLES)
        x_reverse = sum(m.x[j, i, k] for k in m.VEHICLES)
        return m.p[i] - m.p[j] + N * x_forward + (N - 2) * x_reverse <= N - 1
    return Constraint.Skip


# --- Inventory Balance (stations only) ---
def inventory_balance_rule(m, i):
    """Final inventory = initial + dropoffs - pickups, summed over the fleet
    (only the serving vehicle contributes nonzero terms)."""
    pickups = sum(m.u[i, k] for k in m.VEHICLES)
    dropoffs = sum(m.v[i, k] for k in m.VEHICLES)
    return m.b_final[i] == m.b[i] + dropoffs - pickups


# --- Vehicle Load Tracking (per vehicle) ---
def load_lower_rule(m, i, j, k):
    return m.w[j, k] >= m.w[i, k] - m.v[j, k] + m.u[j, k] - m.M_low[j] * (1 - m.x[i, j, k])


def load_upper_rule(m, i, j, k):
    return m.w[j, k] <= m.w[i, k] - m.v[j, k] + m.u[j, k] + m.M_up[j] * (1 - m.x[i, j, k])


def initial_load_rule(m, k):
    """Each vehicle leaves the start depot carrying exactly what it loaded."""
    return m.w[DEPOT_START, k] == m.u[DEPOT_START, k]


def final_load_rule(m, k):
    """Each vehicle returns empty to the end depot."""
    return m.w[DEPOT_END, k] == 0


# --- Operational Bounds ---
def buffer_lower_rule(m, i):
    return m.b_final[i] >= m.B


def buffer_upper_rule(m, i):
    return m.b_final[i] <= m.c[i] - m.B


def pickup_visit_rule(m, i, k):
    """Linking: a vehicle can only pick up at a node it departs from. At the
    start depot b == Q, so this doubles as the depot loading link."""
    visited = sum(m.x[i_arc, j, k] for (i_arc, j) in m.ARCS if i_arc == i)
    return m.u[i, k] <= m.b[i] * visited


def delivery_visit_rule(m, j, k):
    """Linking: a vehicle can only drop off at a node it travels into."""
    visited = sum(m.x[i, j_arc, k] for (i, j_arc) in m.ARCS if j_arc == j)
    return m.v[j, k] <= (m.c[j] - m.b[j]) * visited


def depot_source_capacity_rule(m):
    """The fleet collectively sources at most S bikes from the start depot."""
    return sum(m.u[DEPOT_START, k] for k in m.VEHICLES) <= m.S


def depot_sink_capacity_rule(m):
    """The fleet collectively returns at most S bikes to the end depot."""
    return sum(m.v[DEPOT_END, k] for k in m.VEHICLES) <= m.S


# --- Pickup/Delivery Exclusivity (stations only) ---
def pickup_direction_rule(m, i, k):
    return m.u[i, k] <= m.b[i] * m.y[i]


def delivery_direction_rule(m, i, k):
    return m.v[i, k] <= (m.c[i] - m.b[i]) * (1 - m.y[i])


# --- Time Budget (per vehicle) ---
def time_budget_rule(m, k):
    """Each vehicle's route independently respects the operating window.

    Depot handling counts loading at the start depot and unloading at the end
    depot: returning bikes incur the same per-bike handling time as a station
    dropoff, so both u[depot_start] and v[depot_end] are charged."""
    travel_time = sum(m.ttime[i, j] * m.x[i, j, k] for (i, j) in m.ARCS)
    station_time = sum(
        m.s * sum(m.x[i_arc, j, k] for (i_arc, j) in m.ARCS if i_arc == i)
        + m.tau * (m.u[i, k] + m.v[i, k])
        for i in m.STATIONS
    )
    depot_time = m.tau * (m.u[DEPOT_START, k] + m.v[DEPOT_END, k])
    return travel_time + station_time + depot_time <= m.T


# --- Symmetry Breaking ---
def symmetry_break_rule(m, k):
    """Identical vehicles are used in index order: vehicle k is used only if
    vehicle k-1 is used."""
    if k == m.VEHICLES.first():
        return Constraint.Skip
    prev = m.VEHICLES.prev(k)
    leave_k = sum(m.x[i, j, k] for (i, j) in m.ARCS if i == DEPOT_START)
    leave_prev = sum(m.x[i, j, prev] for (i, j) in m.ARCS if i == DEPOT_START)
    return leave_prev >= leave_k
