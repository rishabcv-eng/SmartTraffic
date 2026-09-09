# Benchmark Plan and Results

SmartTraffic does not claim improvement until repeatable experiments demonstrate
it. Every experiment records the seed, scenario, controller configuration and
simulator version.

Regenerate everything below with:

```bash
cd backend && python -m pytest -q          # 91 regression tests
curl 'localhost:8000/api/benchmark/suite?steps=180'
```

## Baselines and controllers

| Controller | Idea |
| --- | --- |
| `fixed-time` | Conventional fixed clock. The thing cities run today. |
| `actuated` | Detector-actuated with minimum green and hysteresis. |
| `max-pressure` | Serve the larger opposing queue pair. |
| `network-max-pressure` | Movement pressure net of the downstream receiving approach. |
| `predictive-pressure-v2` | Max-pressure on short-horizon forecast queues. |
| `mpc-lite-v1` | Short-horizon scoring with spillback and switching penalties. |
| `transit-priority-v1` | Pressure measured in **people**, not vehicles. |
| `rl-q-learning-v1` | Tabular Q-learning policy, always behind the safety shield. |

All benchmark runs are **shielded by default** (`SafetyShield`), because that is
the configuration a city would deploy: minimum green, maximum green, a
guaranteed pedestrian wait, and fault fallback. Pass `shielded=false` for an
ablation of the raw optimiser.

## Scenarios

- Balanced normal demand
- Directional rush-hour surge
- Road-capacity reduction / incident
- Oversaturated corridor and spillback
- Emergency vehicle passage
- Sensor dropout, stuck detector, comms loss, signal-head failure
- Weather-reduced saturation flow (rain, heavy rain, fog)

## Metrics

Averages alone are not enough — they hide a starved approach — so the suite
reports the distribution and the equity metrics beside them:

- Mean, p50, p95 and maximum vehicle delay
- Worst per-approach wait and which approach it was
- Mean **person** delay (occupancy-weighted) and mean bus delay
- Mean and p95 pedestrian wait
- Network throughput, peak queue, phase switches
- Emergency journey time and red-light waits
- Idle fuel, CO₂ and rupee cost (see `docs/IMPACT.md`)

## Result: adaptive control wins under normal demand

Pooled over seeds `[3, 7, 11, 19, 29]`, 180 ticks, mock engine, shielded,
measured as mean network queue against the fixed-time baseline:

| Controller | Mean queue | vs fixed-time |
| --- | --- | --- |
| `mpc-lite-v1` | 86.9 | **+8.0%** |
| `actuated` | 88.4 | +6.5% |
| `max-pressure` | 90.4 | +4.3% |
| `network-max-pressure` | 91.1 | +3.6% |
| `transit-priority-v1` | 93.4 | +1.2% |
| `predictive-pressure-v2` | 94.3 | +0.2% |
| `fixed-time` | 94.5 | — |
| `rl-q-learning-v1` | 104.0 | −10.0% |

## Result: every adaptive controller *loses* under oversaturation

Same seeds and settings, `rush` demand:

| Controller | Mean queue | vs fixed-time |
| --- | --- | --- |
| `fixed-time` | 775.6 | — |
| `predictive-pressure-v2` | 812.4 | −4.8% |
| `network-max-pressure` | 815.5 | −5.2% |
| `actuated` | 819.6 | −5.7% |
| `max-pressure` | 820.6 | −5.8% |
| `mpc-lite-v1` | 834.6 | −7.6% |
| `transit-priority-v1` | 837.1 | −7.9% |
| `rl-q-learning-v1` | 843.1 | −8.7% |

This is not a bug, and it is not noise — the sign is consistent across all five
seeds. It is a known failure mode of queue-chasing control. Once **every**
approach is saturated, total service capacity is the binding constraint, not the
allocation of green between approaches. A pressure controller then spends green
on the longest queue even when that movement's downstream link is full, so the
discharge goes nowhere, while an even round-robin at least keeps every movement
draining at capacity.

Three honest consequences:

1. **Do not quote a single headline improvement figure.** The number depends on
   the demand regime. Quote the regime with it.
2. **Oversaturation needs a different mechanism** — gating and metering at the
   corridor entry, or explicitly refusing to serve a movement whose downstream
   is blocked. Queue-chasing cannot fix a capacity deficit.
3. **The current `rush` scenario is too extreme to be a useful headline.** At a
   1.8–2.2× arrival multiplier the network never recovers within the run, so it
   measures gridlock rather than control quality. A calibrated peak from real
   counts would be a better demonstration case.

`rl-q-learning-v1` being worst in both regimes is also worth stating plainly:
30 training episodes on a coarse 5×5×2 state space is not enough, and the
result should be read as "shielded RL is wired up and safe", not "RL works
here yet".

## Known limitations

- The mock engine is a development harness, not a traffic simulator. **Final
  performance claims must be regenerated in SUMO/TraCI.**
- Demand is uncalibrated unless counts are supplied via `POST /api/calibrate`.
- Impact figures inherit every assumption in `docs/IMPACT.md`, particularly the
  annualisation factor.
- Confidence intervals from `POST /api/whatif` use a normal approximation, which
  is coarse at the small seed counts used in the UI.
