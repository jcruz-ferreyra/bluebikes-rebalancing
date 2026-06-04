# bluebikes_rebalancing/model/constraints.py

from pyomo.environ import Constraint


# --- Route Structure ---
def leave_depot_rule(m):
    return sum(m.x[i, j] for (i, j) in m.ARCS if i == "depot_start") == 1


def enter_depot_rule(m):
    return sum(m.x[i, j] for (i, j) in m.ARCS if j == "depot_end") == 1


def no_return_start_rule(m, i, j):
    if j == "depot_start":
        return m.x[i, j] == 0
    return Constraint.Skip


def no_depart_end_rule(m, i, j):
    if i == "depot_end":
        return m.x[i, j] == 0
    return Constraint.Skip


def flow_conservation_rule(m, k):
    inflow = sum(m.x[i, j] for (i, j) in m.ARCS if j == k)
    outflow = sum(m.x[i, j] for (i, j) in m.ARCS if i == k)
    return inflow == outflow


def visit_once_rule(m, k):
    return sum(m.x[i, j] for (i, j) in m.ARCS if j == k) <= 1


# --- MTZ Subtour Elimination ---
def mtz_rule(m, i, j):
    N = len(m.STATIONS)
    if i in m.STATIONS and j in m.STATIONS:
        return m.p[i] - m.p[j] + N * m.x[i, j] <= N - 1
    return Constraint.Skip


# --- Inventory Balance ---
def inventory_balance_rule(m, i):
    return m.b_final[i] == m.b[i] + m.v[i] - m.u[i]


# --- Vehicle Load Tracking ---
def load_lower_rule(m, i, j):
    return m.w[j] >= m.w[i] - m.v[j] + m.u[j] - m.M_low[j] * (1 - m.x[i, j])


def load_upper_rule(m, i, j):
    return m.w[j] <= m.w[i] - m.v[j] + m.u[j] + m.M_up[j] * (1 - m.x[i, j])


def initial_load_rule(m):
    return m.w["depot_start"] == m.u["depot_start"]


def final_load_rule(m):
    return m.w["depot_end"] == 0


# --- Operational Bounds ---
def buffer_lower_rule(m, i):
    return m.b_final[i] >= m.B


def buffer_upper_rule(m, i):
    return m.b_final[i] <= m.c[i] - m.B


def pickup_visit_rule(m, i):
    visited = sum(m.x[i_arc, j] for (i_arc, j) in m.ARCS if i_arc == i)
    return m.u[i] <= m.b[i] * visited


def delivery_visit_rule(m, j):
    visited = sum(m.x[i, j_arc] for (i, j_arc) in m.ARCS if j_arc == j)
    return m.v[j] <= (m.c[j] - m.b[j]) * visited


# --- Time Budget ---
def time_budget_rule(m):
    travel_time = sum(m.ttime[i, j] * m.x[i, j] for (i, j) in m.ARCS)
    station_time = sum(
        m.s * sum(m.x[i_arc, j] for (i_arc, j) in m.ARCS if i_arc == i) + m.tau * (m.u[i] + m.v[i])
        for i in m.STATIONS
    )
    depot_time = m.tau * (m.u["depot_start"] + m.v["depot_end"])
    return travel_time + station_time + depot_time <= m.T
