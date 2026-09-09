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

## M8 — Oversaturation *(new, open research)*
- [ ] Gating and metering at corridor entry
- [ ] Refuse to serve movements whose downstream is blocked
- [ ] Re-run the rush benchmark once a calibrated peak replaces the synthetic one

Adaptive control currently **loses to fixed-time** under heavy oversaturation.
This is measured and reproducible — see `docs/BENCHMARKS.md`. It is the most
important open problem in the project.
