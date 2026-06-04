# Problem Formulation

## Problem Structure

**Stations and Nodes:**

- $N$ stations indexed $i \in \{1,\ldots,N\}$
- Depot start: node $0$
- Depot end: node $N+1$
- Total nodes: $N+2$

**Arcs:**

- $N(N-1)$ arcs between stations
- $2N$ arcs connecting depots to stations

**Station Parameters:**

- $b_i$: current inventory (bikes present at start of rebalancing window)
- $d_i$: forecasted net demand $=$ dropoffs $-$ pickups
- $c_i$: docking capacity
- $t_i = \frac{c_i}{2} - d_i$: target inventory after rebalancing

**Depot Configuration:**

- $b_0 = c_0 = Q$: start depot initialized at full truck capacity
- $b_{N+1} = 0$, $c_{N+1} = Q$: end depot empty, absorbs returning bikes
- Mimics real operations where the van sources and returns bikes from a central facility

**Vehicle:**

- Single vehicle with capacity $Q$

**Buffer Parameter:**

- $B$: minimum required bikes and free docks at each station after rebalancing
- Ensures minimum service level is maintained immediately after the rebalancing window

---

## Decision Variables

**Routing**

$x_{i,j} \in \{0,1\}$ for $i,j \in \{0,1,\ldots,N+1\},\ i \neq j$
*Binary: 1 if the vehicle travels from node $i$ to node $j$*

**Bike Operations**

$u_i \in \mathbb{Z}_+$, $\quad 0 \leq u_i \leq b_i$
*Bikes picked up at node $i$*

$v_i \in \mathbb{Z}_+$, $\quad 0 \leq v_i \leq c_i - b_i$
*Bikes dropped off at node $i$*

$b_i^F \in \mathbb{Z}_+$, $\quad 0 \leq b_i^F \leq c_i$
*Final inventory at node $i$ after rebalancing*

*All defined for $i \in \{0, 1, \ldots, N+1\}$*

**Vehicle Load**

$w_i \in \mathbb{Z}_+$, $\quad 0 \leq w_i \leq Q$
*Bikes on the vehicle when leaving node $i$, for $i \in \{0, 1, \ldots, N+1\}$*

**Route Position (MTZ)**

$p_i \in [1, N]$ for $i \in \{1,\ldots,N\}$
*Position of station $i$ in the route sequence (stations only, depots excluded)*

---

## Objective Function

$$Z = \alpha \sum_{i=0}^{N+1} \sum_{\substack{j=0\\j \neq i}}^{N+1} \text{dist}_{ij} \cdot x_{ij} + \beta \sum_{i=1}^{N} (b_i^F - t_i)^2$$

**Routing cost** — $\alpha \cdot$ total distance traveled

**Service quality penalty** — $\beta \cdot$ squared deviations from target inventory

*The ratio $\alpha/\beta$ controls the tradeoff between minimizing distance and maximizing service quality. The quadratic penalty encourages balanced deviations across stations rather than concentrating errors at a few.*

---

## Constraints

**1. Route Structure**

**Leave start-depot once:**
$$\sum_{j=1}^{N} x_{0,j} = 1$$

**Enter end-depot once:**
$$\sum_{i=1}^{N} x_{i,N+1} = 1$$

**Cannot return to start-depot:**
$$x_{i,0} = 0 \quad \forall i \in \{1,\ldots,N+1\}$$

**Cannot depart from end-depot:**
$$x_{N+1,j} = 0 \quad \forall j \in \{0,\ldots,N+1\}$$

**Flow conservation:**
$$\sum_{\substack{i=0\\i \neq k}}^{N+1} x_{i,k} = \sum_{\substack{j=0\\j \neq k}}^{N+1} x_{k,j} \quad \forall k \in \{1,\ldots,N\}$$

**Visit each station at most once:**
$$\sum_{\substack{i=0\\i \neq k}}^{N+1} x_{i,k} \leq 1 \quad \forall k \in \{1,\ldots,N\}$$

**2. Subtour Elimination (MTZ)**

$$p_i - p_j + N \cdot x_{i,j} \leq N - 1 \quad \forall i,j \in \{1,\ldots,N\}, i \neq j$$

$$1 \leq p_i \leq N \quad \forall i \in \{1,\ldots,N\}$$

*Position variables assigned to stations only. Prevents the vehicle from completing sub-routes that do not pass through the depot.*

**3. Inventory Balance**

$$b_i^F = b_i + v_i - u_i \quad \forall i \in \{0, 1,\ldots,N+1\}$$

**4. Vehicle Load Tracking**

$$w_j \geq w_i - v_j + u_j - M^{\text{low}}_j (1 - x_{i,j}) \quad \forall i,j \in \{0,\ldots,N+1\}, i \neq j$$

$$w_j \leq w_i - v_j + u_j + M^{\text{up}}_j (1 - x_{i,j}) \quad \forall i,j \in \{0,\ldots,N+1\}, i \neq j$$

$$w_0 = u_0 \qquad w_{N+1} = 0$$

*Node indexed big M, sized separately per side:*
$$M^{\text{low}}_j = Q + b_j \qquad M^{\text{up}}_j = Q + (c_j - b_j)$$

*When $x_{i,j} = 1$ the pair collapses to $w_j = w_i - v_j + u_j$, enforcing exact load tracking. When $x_{i,j} = 0$ each inequality goes vacuous. The two sides have different worst cases: the lower constraint must cover the expression running high through pickups at $j$ (bounded by $Q + b_j$), the upper must cover it running low through dropoffs at $j$ (bounded by $Q + (c_j - b_j)$). Sizing each to its own bound keeps the relaxation as tight as possible. The formula holds for the depots too: at $N+1$ it gives $M^{\text{low}} = Q$, $M^{\text{up}} = 2Q$, with no special casing.*

**5. Operational Bounds**

**Variable bounds** (encoded directly in the model):
$$0 \leq u_i \leq b_i \quad 0 \leq v_i \leq c_i - b_i \quad 0 \leq b_i^F \leq c_i \quad \forall i \in \{0,\ldots,N+1\}$$

**Buffer constraint** (stations only):
$$B \leq b_i^F \leq c_i - B \quad \forall i \in \{1,\ldots,N\}$$

**Linking constraints:**
$$u_i \leq b_i \sum_{\substack{j=0\\j \neq i}}^{N+1} x_{i,j} \quad \forall i \in \{0,\ldots,N+1\}$$

$$v_j \leq (c_j - b_j) \sum_{\substack{i=0\\i \neq j}}^{N+1} x_{i,j} \quad \forall j \in \{0,\ldots,N+1\}$$

**6. Time Budget**

$$\sum_{i,j} \tau_{ij} \cdot x_{ij} + \sum_{i=1}^{N} \left(s \cdot \sum_{j} x_{ij} + \delta \cdot (u_i + v_i)\right) + \delta \cdot u_0 \leq T_{\max}$$

*Where $\tau_{ij}$ is travel time, $s$ is fixed service time per stop, $\delta$ is time per bike handled, and $T_{\max} = 180$ minutes.*

---
