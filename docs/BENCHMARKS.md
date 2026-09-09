# Benchmark Plan and Results

SmartTraffic does not claim improvement until repeatable experiments demonstrate
it. Every experiment records the seed, scenario, controller configuration and
simulator version.

Regenerate with:

```bash
cd backend && python -m pytest -q          # 104 regression tests
curl 'localhost:8000/api/benchmark/suite?steps=180'
```

## Controllers

| Controller | Idea |
| --- | --- |
| `fixed-time` | Conventional fixed clock. The thing cities run today. |
| `actuated` | Detector-actuated with minimum green and hysteresis. |
| `max-pressure` | Serve the larger opposing queue pair. |
| `network-max-pressure` | Movement pressure net of the downstream receiving approach. |
| `predictive-pressure-v2` | Max-pressure on short-horizon forecast queues. |
| `mpc-lite-v1` | Short-horizon scoring with spillback and switching penalties. |
| `transit-priority-v1` | Pressure measured in **people**, not vehicles. |
| `gated-pressure-v1` | Scores the discharge a movement can *actually* achieve, capped by downstream space. |
| `coordinated-pressure-v1` | Picks one phase for the **network**, letting a junction deviate only on an overwhelming local case. |
| `rl-network-v2` | Tabular Q-learning policy, always behind the safety shield. |

All runs are **shielded by default** (`SafetyShield`): minimum green, maximum
green, a guaranteed pedestrian wait, and fault fallback. Pass `shielded=false`
for an ablation of the raw optimiser.

## Headline result

Pooled over seeds `[3, 7, 11, 19, 29]`, 180 ticks, mock engine, shielded.

### Normal demand

| Controller | Mean queue | vs fixed | Throughput | vs fixed | p95 delay |
| --- | --- | --- | --- | --- | --- |
| `coordinated-pressure-v1` | 68.4 | **+28.0%** | 2198 | **+0.4%** | **10.0** |
| `mpc-lite-v1` | 86.9 | +8.5% | 2165 | −1.0% | 11.6 |
| `actuated` | 88.4 | +7.0% | 2164 | −1.1% | 11.4 |
| `max-pressure` | 90.4 | +4.8% | 2159 | −1.3% | 11.6 |
| `gated-pressure-v1` | 91.0 | +4.2% | 2160 | −1.3% | 12.0 |
| `network-max-pressure` | 91.1 | +4.0% | 2153 | −1.6% | 12.0 |
| `transit-priority-v1` | 93.4 | +1.6% | 2161 | −1.2% | 12.2 |
| `predictive-pressure-v2` | 94.3 | +0.7% | 2151 | −1.7% | 12.0 |
| `fixed-time` | 95.0 | — | 2188 | — | 14.0 |
| `rl-network-v2` | 131.9 | −38.8% | 1963 | −10.3% | 27.0 |

### Rush (oversaturated)

| Controller | Mean queue | vs fixed | Throughput | vs fixed | p95 delay |
| --- | --- | --- | --- | --- | --- |
| `fixed-time` | 292.9 | — | 2676 | — | 27.2 |
| `coordinated-pressure-v1` | 303.1 | −3.5% | **2703** | **+1.0%** | **25.8** |
| `predictive-pressure-v2` | 352.9 | −20.5% | 2630 | −1.7% | 29.0 |
| `max-pressure` | 354.1 | −20.9% | 2618 | −2.1% | 29.6 |
| `gated-pressure-v1` | 354.5 | −21.0% | 2629 | −1.7% | 29.2 |
| `mpc-lite-v1` | 356.9 | −21.8% | 2615 | −2.3% | 29.8 |
| `transit-priority-v1` | 369.1 | −26.0% | 2580 | −3.6% | 32.2 |

## How the oversaturation defect was found and fixed

An earlier revision of this document reported that **every** adaptive controller
lost to a fixed clock under saturation, by 5–8%. That was real, reproducible
across all five seeds — and it had two separate causes, one a modelling bug and
one a genuine control-design error.

### Cause 1: the engine had unbounded link storage

Approaches were holding 191 vehicles. A real 200 m two-lane approach holds about
40. With unbounded storage, a green could always discharge into a downstream
link that was already full, which is bookkeeping rather than traffic. It also
broke max-pressure's central assumption: the pressure signal only means anything
when a blocked link can actually refuse vehicles.

Adding `LINK_STORAGE = 40` with physical spillback blocking shrank the gap from
−5..−8% to about −2%, and bounded the queues (776 → 293).

### Cause 2: local optimisation destroys progression

The remaining gap was the real finding. A fixed clock switches every junction
*in unison*, which accidentally implements a green wave along this network's
platoon chains — a vehicle discharged by J1 arrives at J3 to find the same phase
still running. Controllers that optimise each junction independently maximise
local pressure and destroy that alignment, so platoons stop at every junction
and lose more to stopping than local optimisation ever wins back.

The test that confirmed it: a deliberately crude controller that computes
pressure network-wide and applies one phase everywhere beat both fixed-time and
max-pressure immediately. `coordinated-pressure-v1` is that idea done properly —
coordination by default, with capacity-aware scoring and a high bar for a single
junction to break ranks.

**The lesson generalises beyond this project: on a corridor, coordination is
worth more than local optimality.** That is also why `docs/ALGORITHMS.md` and
the green-wave module exist; this result is the empirical case for them.

### Why deviation almost never fires

In this topology every phase at every junction contains at least one movement
that exits the network, so no phase can ever be *fully* blocked and holding the
coordinated phase is almost never wasteful. Across 180 ticks × 4 junctions the
deviation threshold fires 0 times in clean running and twice under an accident.
On a network where a phase can be completely blocked it would earn its keep far
more often. This is asserted in `tests/test_coordination.py`.

## Two metric traps this exposed

**1. Average queue can be gamed by refusing demand.** Under rush,
`rl-network-v2` has the *lowest* mean queue of any controller (278.8, better
than fixed-time) while having the *worst* throughput (−10.3%) and a catastrophic
p95 (66.2 vs 27.2). It scores well because it lets fewer vehicles into the
network — blocked demand does not appear in a queue-length metric. Under
saturation, **throughput and `blocked_arrivals` are the honest metrics**, not
mean queue.

**2. Averages hide starvation.** This is why every table here carries p95
alongside the mean, and why the suite reports the worst per-approach wait.

## Scenarios and metrics

Scenarios: balanced normal demand, directional rush surge, capacity-reducing
accident, oversaturated corridor with spillback, emergency passage, sensor and
signal faults, weather-reduced saturation flow.

Metrics: mean / p50 / p95 / max vehicle delay; worst per-approach wait; person
and bus delay; pedestrian mean and p95 wait; throughput; peak queue; phase
switches; blocked arrivals; spillback-blocked movements; emergency journey time;
and the fuel / CO₂ / rupee conversion in `docs/IMPACT.md`.

## Known limitations

- The mock engine is a development harness, not a traffic simulator. **Final
  performance claims must be regenerated in SUMO/TraCI.** In particular, the
  coordination result should be re-tested on a network whose geometry was not
  chosen by us.
- Demand is uncalibrated unless counts are supplied via `POST /api/calibrate`.
- Confidence intervals use a normal approximation, coarse at small seed counts.

## Two metric traps found while benchmarking

Both were found by the benchmark itself, and both would have produced a
confident, wrong headline number.

**Average queue rewards refusing traffic.** With finite link storage, an
approach held at red fills to capacity and then turns arrivals away at the
boundary. Those vehicles never enter the network, so they never appear in the
queue statistic. Plain fixed-time blocks roughly 100 more vehicles per run than
`coordinated-pressure-v1` and posts a 3.5% *shorter* mean queue for it, while
serving fewer vehicles overall. Ranking is therefore on demand actually served
first, with queue only breaking ties among controllers that served the same
share of demand. At normal demand nothing is blocked and this reduces to the
old queue ranking.

**Mean delay hides starvation.** The first RL controller posted the lowest mean
queue of any controller under rush while running a p95 delay of 66 ticks
against fixed-time's 27. It had learned to keep a couple of approaches
permanently red. Every headline claim here is reported alongside p95 and
worst-approach wait for that reason.

## Negative results worth recording

Four refinements to `coordinated-pressure-v1` were implemented, measured over
8 seeds with paired confidence intervals, and **rejected**:

| change | outcome |
|---|---|
| downstream relief (count space the receiving link frees this same step) | zero effect on every seed — with storage 40 and capacity 5, room is essentially never the binding constraint |
| fairness term on accumulated red | lower throughput, more blocked arrivals |
| explicit switching cost | no gain beyond the shield's existing minimum green |
| exit-movement priority | +8.8 throughput ± 11.6, i.e. inside the noise |

The controller is at the ceiling for this network geometry. Further gains need
a richer engine — turning movements, lane-level storage, real travel times —
rather than a better objective on this one. The v2 controller built for these
experiments was deleted rather than shipped, since it changed nothing.

## What did work: coordination generalises

Rewriting the RL controller to choose one phase for the **whole network**
instead of running an independent agent per junction moved it from 39% worse
than fixed-time at normal demand to roughly 25% better — worst controller to
second best, with no change to the learning algorithm itself. Its reward was
also changed from negative queue length to vehicles discharged minus demand
turned away, which closes the metric trap above. This is the same result the
coordinated controller demonstrates, arrived at independently: on this network,
phase alignment matters more than local optimisation.
- Confidence intervals from `POST /api/whatif` use a normal approximation, which
  is coarse at small seed counts.
