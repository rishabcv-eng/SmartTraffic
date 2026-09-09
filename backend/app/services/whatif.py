"""What-if console: answer planning questions with confidence intervals.

A single simulation run is an anecdote. A city engineer asking "what happens if
demand grows 20% and we lose a lane on the west approach?" needs an answer with
an error bar on it, not one number from one random seed.

Every question is answered by replaying the same seeds under both the baseline
and the candidate, so the comparison is paired: the difference is measured on
identical demand, which removes most of the run-to-run noise.
"""

from __future__ import annotations

from math import sqrt
from statistics import mean, stdev

from app.controllers.registry import DEFAULT_CONTROLLER
from app.services.scenario import ScenarioConfig, simulate

#: Normal approximation for a 95% interval. Fine for the seed counts used here.
Z95 = 1.96

DEFAULT_SEEDS = [3, 7, 11, 19, 29, 37, 41, 53]


def _interval(values: list[float]) -> dict:
    if not values:
        return {'mean': 0.0, 'ci_low': 0.0, 'ci_high': 0.0, 'stdev': 0.0, 'n': 0}
    avg = mean(values)
    sd = stdev(values) if len(values) > 1 else 0.0
    half = Z95 * sd / sqrt(len(values)) if len(values) > 1 else 0.0
    return {
        'mean': round(avg, 3),
        'ci_low': round(avg - half, 3),
        'ci_high': round(avg + half, 3),
        'stdev': round(sd, 3),
        'n': len(values),
    }


def run_whatif(
    controllers: list[str] | None = None,
    baseline: str = 'fixed-time',
    seeds: list[int] | None = None,
    steps: int = 180,
    scenario: str = 'normal',
    demand_multiplier: float = 1.0,
    weather: str = 'clear',
    pedestrian_rate: float = 1.0,
    lane_closure: dict | None = None,
    event: str | None = None,
    shielded: bool = True,
) -> dict:
    """Compare controllers under one set of conditions, across many seeds.

    ``lane_closure`` is expressed as a fault, e.g.
    ``{'kind': 'signal-fault', 'junction': 'J3'}`` or a detector failure.
    """
    seeds = seeds or DEFAULT_SEEDS
    controllers = controllers or [baseline, DEFAULT_CONTROLLER, 'mpc-lite-v1']
    if baseline not in controllers:
        controllers = [baseline] + controllers

    faults = [lane_closure] if lane_closure else []
    runs: dict[str, list[dict]] = {}

    for name in controllers:
        rows = []
        for seed in seeds:
            rows.append(simulate(ScenarioConfig(
                controller=name,
                steps=steps,
                seed=seed,
                scenario=scenario,
                event=event,
                weather=weather,
                demand_multiplier=demand_multiplier,
                pedestrian_rate=pedestrian_rate,
                faults=faults,
                shielded=shielded,
            )))
        runs[name] = rows

    tracked = {
        'average_network_queue': lambda r: r['average_network_queue'],
        'mean_vehicle_delay': lambda r: r['metrics']['mean_vehicle_delay'],
        'p95_vehicle_delay': lambda r: r['metrics']['p95_vehicle_delay'],
        'mean_person_delay': lambda r: r['metrics']['mean_person_delay'],
        'mean_pedestrian_delay': lambda r: r['metrics']['mean_pedestrian_delay'],
        'worst_approach_wait': lambda r: r['metrics']['worst_approach_wait'],
        'throughput': lambda r: float(r['throughput']),
        'co2_kg': lambda r: r['impact']['co2_kg'],
    }

    results = []
    for name in controllers:
        rows = runs[name]
        summary = {metric: _interval([fn(r) for r in rows]) for metric, fn in tracked.items()}
        entry = {'controller': name, 'metrics': summary}

        if name != baseline:
            base_rows = runs[baseline]
            deltas = {}
            for metric, fn in tracked.items():
                paired = [fn(b) - fn(c) for b, c in zip(base_rows, rows)]
                interval = _interval(paired)
                # Paired: the improvement is credible when the whole interval
                # sits on one side of zero.
                interval['significant'] = (
                    interval['ci_low'] > 0 or interval['ci_high'] < 0
                ) if len(paired) > 1 else False
                base_mean = mean([fn(b) for b in base_rows])
                interval['improvement_pct'] = round(
                    100.0 * interval['mean'] / max(1e-9, abs(base_mean)), 2
                )
                deltas[metric] = interval
            entry['vs_baseline'] = deltas
        results.append(entry)

    return {
        'question': {
            'scenario': scenario,
            'demand_multiplier': demand_multiplier,
            'weather': weather,
            'pedestrian_rate': pedestrian_rate,
            'lane_closure': lane_closure,
            'event': event,
            'steps': steps,
            'seeds': seeds,
            'shielded': shielded,
        },
        'baseline': baseline,
        'results': results,
        'reading': (
            'Reductions are baseline minus candidate, so positive means better. '
            'An interval that does not span zero is a difference worth reporting; '
            'one that does is inside the noise of the seeds tested.'
        ),
    }
