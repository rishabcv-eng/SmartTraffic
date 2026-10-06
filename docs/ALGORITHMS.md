# SmartTraffic controller stack

SmartTraffic deliberately compares simple and increasingly network-aware controllers before adopting any learned policy.

## Controllers

1. **Fixed-time** — identical pre-timed cycle at every junction. This is the basic baseline.
2. **Actuated** — responds to local opposing queue pairs with minimum-green hysteresis.
3. **Local max-pressure** — serves the larger local NS/EW queue pair at each junction.
4. **Network max-pressure** — scores each movement using `upstream queue - downstream receiving queue`, so a junction does not blindly discharge vehicles into an already blocked downstream approach.
5. **Predictive pressure v2** — forecasts each directional approach using its recent queue trend, then applies network max-pressure to those short-horizon forecasts. A small switch penalty reduces phase chattering.
6. **MPC-lite v1 (experimental)** — retained as an experimental branch because early mock-engine results showed that its coarse whole-junction downstream penalty can underperform simpler controllers. We keep losing ideas visible instead of hiding them.

## Development benchmark

`GET /api/benchmark/suite` evaluates every controller over multiple random seeds and four scenarios:

- normal demand
- rush demand
- accident
- rush + accident

Metrics include:

- mean network queue
- queue standard deviation
- throughput
- peak queue
- phase switches
- percentage improvement versus fixed-time

The suite is deterministic for a given seed set. It is a **development benchmark only**. Final performance claims must be regenerated using SUMO/TraCI on imported road networks.

## Why predictive pressure v2

The original predictive controller penalized an entire downstream junction queue. Experiments showed that this can over-penalize harmless movements and perform worse than fixed-time. Version 2 instead models pressure at the movement/receiving-approach level, which is closer to the actual propagation mechanism in the simulated network.

This project follows an iterative rule: an algorithm is kept only if it survives reproducible comparison against simpler baselines.
