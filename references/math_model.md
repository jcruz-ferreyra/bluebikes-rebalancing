# Problem Formulation (Multi-Vehicle)

## Problem Structure

**Stations and Nodes:**

- $N$ stations indexed $i \in \{1,\ldots,N\}$
- Depot start: node $0$
- Depot end: node $N+1$
- Total nodes: $N+2$

**Arcs:**

- Routing variables $x_{i,j,k}$ are defined over the full arc set $A = \{(i,j) : i,j \in \{0,\ldots,N+1\},\ i \neq j\}$, of size $(N+2)(N+1)$
- The route structure constraints forbid the infeasible arcs — arcs into the start depot, arcs out of the end depot, and the direct depot-to-depot arc — leaving the effective set a vehicle can actually use: $N(N-1)$ station-to-station arcs, $N$ start-depot-to-station arcs, and $N$ station-to-end-depot arcs, for $N(N+1)$ effective arcs
- The $2(N+1)$ excluded arcs are exactly those zeroed by the no-return-to-start, no-depart-from-end, and no-depot-to-depot rules

**Fleet:**

- $K$ identical vehicles indexed $k \in \{1,\ldots,K\}$
- Each vehicle has capacity $Q$
- All vehicles share the depot: every used vehicle departs node $0$ and returns to node $N+1$
- Fleet size is an upper bound; a vehicle may stay unused
- $\gamma$: fixed cost charged once per deployed vehicle, in the same units as the routing and penalty terms. It attaches to deployment, not to time used, because the truck and driver are paid for the shift regardless of how much of the window is consumed; this also captures asset depreciation and idle time

**Station Parameters:**

- $b_i$: current inventory (bikes present at start of rebalancing window)
- $d_i$: forecasted net demand $=$ dropoffs $-$ pickups
- $c_i$: docking capacity
- $t_i = \frac{c_i}{2} - d_i$: target inventory after rebalancing — half-full capacity shifted by forecast net demand, so $(b_i^F - t_i)$ is the projected end-of-day deviation from half full and the objective penalizes squared end-of-day imbalance. $t_i$ may fall outside $[B, c_i - B]$ or below zero; this is intentional and left unclamped. The buffer still binds $b_i^F$, and any residual penalty floor is real irreducible imbalance, not an infeasibility

**Depot Configuration:**

- Central facility that sources and absorbs bikes for the whole fleet
- Each vehicle leaves loaded with up to $Q$ bikes and returns empty
- The end depot absorbs each vehicle's returning load
- $b_0 = c_0 = Q$: start depot initialized at full truck capacity and sized to hold it
- $b_{N+1} = 0$, $c_{N+1} = Q$: end depot starts empty and absorbs returning bikes up to $Q$
- $S$: total depot capacity, the bikes the fleet can collectively source at the start and return at the end. Set $S = Q$ to preserve the single vehicle assumption

**Buffer Parameter:**

- $B$: minimum required bikes and free docks at each station after rebalancing

---

## Decision Variables

**Routing**

$x_{i,j,k} \in \{0,1\}$ for $i,j \in \{0,\ldots,N+1\},\ i \neq j,\ k \in \{1,\ldots,K\}$
*1 if vehicle $k$ travels from node $i$ to node $j$*

**Bike Operations** (per vehicle)

$u_{i,k} \in \mathbb{Z}_+$, $\quad 0 \leq u_{i,k} \leq b_i$
*Bikes picked up by vehicle $k$ at node $i$*

$v_{i,k} \in \mathbb{Z}_+$, $\quad 0 \leq v_{i,k} \leq c_i - b_i$
*Bikes dropped off by vehicle $k$ at node $i$*

*Depot loading uses $u_{0,k}$ with $0 \leq u_{0,k} \leq Q$; the end depot absorbs via $v_{N+1,k}$*

**Final Inventory** (per station)

$b_i^F \in \mathbb{Z}_+$, $\quad 0 \leq b_i^F \leq c_i \quad \forall i \in \{1,\ldots,N\}$
*Final inventory at station $i$ after rebalancing*

**Direction Selector** (per station)

$y_i \in \{0,1\}$ for $i \in \{1,\ldots,N\}$
*1 if station $i$ operates in pickup mode, 0 if dropoff. One vehicle serves a station, so a single selector governs its direction*

**Vehicle Load** (per vehicle)

$w_{i,k} \in \mathbb{Z}_+$, $\quad 0 \leq w_{i,k} \leq Q$
*Bikes on vehicle $k$ when leaving node $i$*

**Route Position (MTZ)** (per station, fleet wide)

$p_i \in [1, N]$ for $i \in \{1,\ldots,N\}$
*Position of station $i$ within whichever route serves it*

---

## Objective Function

$$Z = \alpha \sum_{k=1}^{K} \sum_{i=0}^{N+1} \sum_{\substack{j=0\\j \neq i}}^{N+1} \text{dist}_{ij} \cdot x_{i,j,k} + \beta \sum_{i=1}^{N} (b_i^F - t_i)^2 + \gamma \sum_{k=1}^{K} \sum_{j=1}^{N} x_{0,j,k}$$

**Routing cost** — $\alpha \cdot$ total distance over all vehicles

**Service quality penalty** — $\beta \cdot$ squared deviations from target inventory

**Deployment cost** — $\gamma \cdot$ number of vehicles used. The inner sum $\sum_{j=1}^{N} x_{0,j,k}$ is the indicator that vehicle $k$ is used: it equals 1 when the vehicle leaves the start depot and 0 otherwise, binary by the leave-at-most-once constraint

*The deployment term makes fleet size endogenous: a vehicle is deployed only when its routing and service benefit exceeds $\gamma$, instead of the fleet always maxing out because any helpful vehicle is free to add.*

---

## Constraints

**1. Route Structure** (per vehicle)

**Leave start-depot at most once:**
$$\sum_{j=1}^{N} x_{0,j,k} \leq 1 \quad \forall k$$

**Enter end-depot at most once:**
$$\sum_{i=1}^{N} x_{i,N+1,k} \leq 1 \quad \forall k$$

**Depot use consistency (leave iff return):**
$$\sum_{j=1}^{N} x_{0,j,k} = \sum_{i=1}^{N} x_{i,N+1,k} \quad \forall k$$

*Logically redundant: summing per-vehicle flow conservation over all nodes (stations cancel, the no-return and no-depart rules zero the depot terms) already forces leave $=$ return. Kept as explicit documentation; it is not the constraint that ties the routes together.*

**Cannot return to start-depot:**
$$x_{i,0,k} = 0 \quad \forall i, k$$

**Cannot depart from end-depot:**
$$x_{N+1,j,k} = 0 \quad \forall j, k$$

**No direct depot-to-depot arc:**
$$x_{0,N+1,k} = 0 \quad \forall k$$

*Without this a vehicle could pair a real departure $x_{0,A,k} = 1$ with $x_{0,N+1,k} = 1$, giving the start depot out-degree two and an extra zero-distance edge the objective is indifferent to. Forbidding it makes the "leave at most once" semantics actually hold.*

**Flow conservation (per vehicle, per station):**
$$\sum_{\substack{i=0\\i \neq h}}^{N+1} x_{i,h,k} = \sum_{\substack{j=0\\j \neq h}}^{N+1} x_{h,j,k} \quad \forall h \in \{1,\ldots,N\}, \forall k$$

**2. Station Assignment** (fleet wide)

**Each station served by at most one vehicle, at most once:**
$$\sum_{k=1}^{K} \sum_{\substack{i=0\\i \neq h}}^{N+1} x_{i,h,k} \leq 1 \quad \forall h \in \{1,\ldots,N\}$$

**3. Subtour Elimination (MTZ)**

$$p_i - p_j + N \sum_{k=1}^{K} x_{i,j,k} \leq N - 1 \quad \forall i,j \in \{1,\ldots,N\}, i \neq j$$

$$1 \leq p_i \leq N \quad \forall i \in \{1,\ldots,N\}$$

*A single position variable suffices: each station lies on one route, and summing $x$ over $k$ makes the coefficient $\sum_k x_{i,j,k} \in \{0,1\}$, so the constraint orders stations within whichever vehicle uses the arc and stays vacuous across routes.*

*MTZ is the loosest standard subtour formulation, and its LP relaxation weakens further as the binary count scales with $K$. It is chosen here for transparency and is correct, not tuned for speed. If fleet-scale solves stall, the first lever is to replace it with lifted Desrochers–Laporte inequalities or a commodity-flow subtour elimination, both of which give a materially tighter relaxation.*

**4. Inventory Balance** (stations only)

$$b_i^F = b_i + \sum_{k=1}^{K} v_{i,k} - \sum_{k=1}^{K} u_{i,k} \quad \forall i \in \{1,\ldots,N\}$$

*Only the serving vehicle contributes a nonzero term, so the sums collapse to that vehicle's operations.*

**5. Vehicle Load Tracking** (per vehicle)

$$w_{j,k} \geq w_{i,k} - v_{j,k} + u_{j,k} - M^{\text{low}}_j (1 - x_{i,j,k}) \quad \forall i,j, i \neq j, \forall k$$

$$w_{j,k} \leq w_{i,k} - v_{j,k} + u_{j,k} + M^{\text{up}}_j (1 - x_{i,j,k}) \quad \forall i,j, i \neq j, \forall k$$

$$w_{0,k} = u_{0,k} \qquad w_{N+1,k} = 0 \qquad \forall k$$

*Node indexed big M, unchanged from the single vehicle case:*
$$M^{\text{low}}_j = Q + b_j \qquad M^{\text{up}}_j = Q + (c_j - b_j)$$

**6. Operational Bounds**

**Buffer constraint** (stations only):
$$B \leq b_i^F \leq c_i - B \quad \forall i \in \{1,\ldots,N\}$$

**Linking constraints** (per vehicle):
$$u_{i,k} \leq b_i \sum_{\substack{j=0\\j \neq i}}^{N+1} x_{i,j,k} \quad \forall i \in \{1,\ldots,N\}, \forall k$$

$$v_{i,k} \leq (c_i - b_i) \sum_{\substack{j=0\\j \neq i}}^{N+1} x_{i,j,k} \quad \forall i \in \{1,\ldots,N\}, \forall k$$

**Depot loading link:**
$$u_{0,k} \leq Q \sum_{j=1}^{N} x_{0,j,k} \quad \forall k$$

**Depot unloading link:**
$$v_{N+1,k} \leq Q \sum_{i=1}^{N} x_{i,N+1,k} \quad \forall k$$

*Sink-side analog of the loading link: forces $v_{N+1,k} = 0$ for a vehicle that never enters the end depot, closing the phantom-unload hole where an unused vehicle would otherwise consume depot capacity $S$ and burn time budget for nothing.*

**Depot capacity** (fleet wide):
$$\sum_{k=1}^{K} u_{0,k} \leq S \qquad \sum_{k=1}^{K} v_{N+1,k} \leq S$$

*Two independent caps of $S$, one on bikes sourced from the start depot and one on bikes absorbed at the end depot. They are not coupled: sourced and absorbed bikes are not assumed to share a single physical stock.*

**Pickup or delivery exclusivity** (stations only):
$$u_{i,k} \leq b_i \, y_i \quad \forall i \in \{1,\ldots,N\}, \forall k$$

$$v_{i,k} \leq (c_i - b_i)(1 - y_i) \quad \forall i \in \{1,\ldots,N\}, \forall k$$

**7. Time Budget** (per vehicle)

$$\sum_{i,j} \tau_{ij} \, x_{i,j,k} + \sum_{i=1}^{N} \left(s \sum_{\substack{j=0\\j \neq i}}^{N+1} x_{i,j,k} + \delta \, (u_{i,k} + v_{i,k})\right) + \delta \, (u_{0,k} + v_{N+1,k}) \leq T_{\max} \quad \forall k$$

*Each vehicle's route independently respects the window. Depot handling charges both the start-depot load $u_{0,k}$ and the end-depot unload $v_{N+1,k}$: returning bikes to the depot is the same per-bike handling as a station dropoff, so omitting the unload term would be an unjustified asymmetry.*

**8. Symmetry Breaking**

$$\sum_{j=1}^{N} x_{0,j,k} \geq \sum_{j=1}^{N} x_{0,j,k+1} \quad \forall k \in \{1,\ldots,K-1\}$$

*Vehicles are identical, so the active subset can be permuted freely, which explodes the search tree. Forcing vehicles to be used in index order removes that symmetry: vehicle $k+1$ is used only if vehicle $k$ is.*

---
