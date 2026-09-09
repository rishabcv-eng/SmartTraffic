# SmartTraffic Roadmap

`[x]` done · `[~]` partial · `[ ]` outstanding

## M0 — Foundation
- [x] Deterministic mock traffic network
- [x] Fixed-time baseline
- [x] Predictive-pressure controller scaffold
- [x] REST/WebSocket API
- [x] Live control-room UI

## M1 — Real SUMO network
- [x] Implement TraCI adapter
- [x] Build controlled four-junction SUMO scenario
- [x] Import a real OSM road network
- [~] Stream lane/edge state to the UI
- [x] Deterministic reset and replay
- [ ] Validate generated traffic-light phases

## M2 — Strong baselines
- [x] Actuated controller
- [x] Max-pressure controller
- [x] Batch benchmark runner
- [x] Delay, queue, throughput, stops and spillback metrics
- [x] p95 / worst-case delay and per-approach fairness metrics

## M3 — Predictive coordination
- [x] Short-horizon arrival/queue predictor
- [x] Downstream spillback forecast
- [x] Coordinated multi-junction controller
- [x] Ablation against max-pressure
- [x] Corridor offset optimisation and time-space diagram
- [ ] Graph/flow predictor replacing the clone-based forecast

## M4 — Visual state ingestion
- [x] Uploaded traffic image to lane/vehicle estimates
- [x] Confidence-aware initialisation (low-confidence estimates are refused)
- [x] Manual correction path with operator provenance
- [ ] Per-camera mask commissioning UI

## M5 — Disturbance handling
- [x] Accident / capacity drop
- [x] Demand surge
- [x] Emergency green corridor, end to end with travel-time measurement
- [x] Sensor and signal fault fallback with an explicit fallback ladder
- [x] Weather-reduced saturation flow

## M6 — SIH demonstration
- [x] Side-by-side baseline vs SmartTraffic simulation
- [x] Reproducible benchmark report
- [x] Operations console: impact, audit, faults, planner
- [~] Real-map animated control room
- [ ] Future congestion overlay on the map view

## M7 — Deployability *(new)*
- [x] Safety shield: min/max green, pedestrian wait guarantee, fault fallback
- [x] Per-decision audit trail with the binding constraint recorded
- [x] Person-throughput objective and bus priority
- [x] Impact model in fuel, CO₂ and rupees with published assumptions
- [x] Demand calibration from observed counts
- [x] What-if planner with confidence intervals
- [x] Hardware-in-the-loop signal heads
- [x] Privacy position documented against DPDP
- [ ] Edge deployment: container, latency budget, offline operation

## M8 — Oversaturation *(largely resolved)*
- [x] Finite link storage with physical spillback blocking
- [x] Count demand that cannot physically enter, rather than dropping it
- [x] Refuse to spend green on movements whose downstream is blocked
      (`gated-pressure-v1`)
- [x] Network-level phase coordination (`coordinated-pressure-v1`) — the actual
      fix; local optimisation was destroying corridor progression
- [ ] Close the remaining 3.5% mean-queue gap against fixed-time under rush
- [ ] Re-run the rush benchmark once a calibrated peak replaces the synthetic one
- [ ] Re-test coordination on a network geometry we did not choose

Adaptive control **used to lose** to fixed-time under saturation. It no longer
does on throughput or p95. The write-up of how that was diagnosed is in
`docs/BENCHMARKS.md` and is worth reading before extending the controllers.
