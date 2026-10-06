# Implementation status

## Fully implemented

- Deterministic connected four-junction traffic lab with per-vehicle tracking,
  so delay percentiles and person-weighted delay are exact rather than inferred
  from queue length.
- Ten controllers: `fixed-time`, `actuated`, `max-pressure`,
  `network-max-pressure`, `predictive-pressure-v2`, `mpc-lite-v1`,
  `transit-priority-v1` (person-weighted), `gated-pressure-v1` (capacity-aware),
  `coordinated-pressure-v1` (network-level phase, the default), and
  `rl-network-v2` (shielded).
- **Finite link storage with physical spillback.** An approach holds 40 vehicles;
  a green cannot discharge into a full link, and demand that cannot enter is
  counted rather than silently dropped.
- **Safety shield** wrapping any controller: minimum green, maximum green
  starvation guard, guaranteed maximum pedestrian wait, emergency preemption,
  and fault fallback — with a per-decision audit trail explaining which
  constraint bound and why.
- **Pedestrians and buses as first-class road users.** Exclusive pedestrian
  phase with a hard wait cap; buses weighted by occupancy in both metrics and
  the transit-priority objective.
- **End-to-end emergency preemption.** A priority vehicle physically traverses
  the network; the shield holds a rolling green corridor ahead of it. The
  comparison endpoint reports travel time with and without preemption *and* the
  cost the rest of the network paid, measured against the same controller.
- **Degraded-mode operation.** Detector dropout, stuck detector, comms loss and
  signal-head failure are injectable. Faults corrupt what the controller
  observes without changing physical truth, and each fault routes to a
  documented fallback.
- **Weather and event modes** reducing saturation flow (rain, heavy rain, fog)
  and raising footfall (stadium egress).
- **Impact model** converting delay into idle fuel, CO₂ and rupees, with every
  assumption published in `docs/IMPACT.md` and overridable per request.
- **Corridor coordination** with offset computation, through-band measurement
  and time-space diagram data.
- **What-if planner** answering planning questions across many seeds with paired
  95% confidence intervals and a significance flag.
- **Demand calibration** from an observed-counts CSV, with a replay that reports
  the residual between observed and simulated flow.
- **Vision pipeline (M4 complete):** detect → bind to approach via a camera mask
  → score confidence → operator correction → seed the controller. Low-confidence
  estimates are refused unless explicitly forced.
- **Hardware-in-the-loop** signal-head feed with an ASCII wire format and ESP32
  firmware, including link-loss fail-safe.
- REST + WebSocket API, React control room with an operations console.
- 104 regression tests.

## Requires an external dependency

- SUMO/TraCI adapter, runtime engine switching via `SMARTTRAFFIC_ENGINE=sumo`,
  demo network files and OSM conversion.
- YOLO detection needs `ultralytics` and local weights; everything downstream of
  detection (lane binding, confidence, correction, seeding) is implemented and
  tested without it.

## Incomplete / research phase

- **Oversaturation — largely resolved.** Adaptive control used to lose to
  fixed-time under saturation. Two causes were found: unbounded link storage in
  the engine, and independent per-junction optimisation destroying corridor
  progression. `coordinated-pressure-v1` now leads on throughput and p95 in both
  regimes, though it still carries a 3.5% higher mean queue than fixed-time under
  rush. See `docs/BENCHMARKS.md`.
- **RL quality.** `rl-network-v2` is wired up and safely shielded, but 30
  training episodes on a coarse state space is not enough; it is currently the
  weakest controller. Treat it as an integration proof, not a result.
- Traffic-light phase validation on generated SUMO networks.
- Large-scale multi-seed SUMO experiments.
- Graph/flow predictor (currently clone-based forecasting).
- Real city corridor integration for the final demonstration.

## Key limitation

The mock engine is a development harness. **Final performance claims must come
from SUMO experiments**, and demand must be calibrated against real counts
before any impact figure is quoted to a city.
