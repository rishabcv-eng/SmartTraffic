from __future__ import annotations

from statistics import mean, pstdev

from app.controllers.registry import CONTROLLERS
from app.services.impact import compare_impact
from app.services.scenario import ScenarioConfig, simulate

#: Benchmarks run behind the safety shield by default, because that is the
#: configuration a city would actually deploy: no controller ships without
#: minimum green, starvation limits and a pedestrian guarantee. Set
#: ``shielded=False`` for an ablation of the raw optimiser.
DEFAULT_SHIELDED = True

BASELINE = 'fixed-time'


def controller_names() -> list[str]:
    return list(CONTROLLERS)


def _single_run(
    name: str,
    *,
    steps: int,
    seed: int,
    scenario: str,
    event: str | None = None,
    event_tick: int = 30,
    shielded: bool = DEFAULT_SHIELDED,
) -> dict:
    result = simulate(ScenarioConfig(
        controller=name,
        steps=steps,
        seed=seed,
        scenario=scenario,
        event=event,
        event_tick=event_tick,
        shielded=shielded,
    ))
    metrics = result['metrics']
    return {
        'controller': name,
        'steps': steps,
        'seed': seed,
        'scenario': scenario,
        'event': event,
        'shielded': shielded,
        'throughput': result['throughput'],
        'average_network_queue': result['average_network_queue'],
        'final_queue': result['final_queue'],
        'peak_queue': result['peak_queue'],
        'phase_switches': result['phase_switches'],
        # Distribution, not just the mean: p95 and worst-case expose the
        # starvation that an average queue length hides.
        'mean_vehicle_delay': metrics['mean_vehicle_delay'],
        'p95_vehicle_delay': metrics['p95_vehicle_delay'],
        'max_vehicle_delay': metrics['max_vehicle_delay'],
        'worst_approach': metrics['worst_approach'],
        'worst_approach_wait': metrics['worst_approach_wait'],
        'mean_person_delay': metrics['mean_person_delay'],
        'mean_bus_delay': metrics['mean_bus_delay'],
        'mean_pedestrian_delay': metrics['mean_pedestrian_delay'],
        'p95_pedestrian_delay': metrics['p95_pedestrian_delay'],
        'pedestrians_served': metrics['pedestrians_served'],
        'blocked_arrivals': metrics['blocked_arrivals'],
        'demand_served_pct': round(
            100.0 * metrics['served_vehicles']
            / max(1e-9, metrics['served_vehicles'] + metrics['blocked_arrivals']), 2),
        'co2_kg': result['impact']['co2_kg'],
        'total_cost_inr': result['impact']['total_cost_inr'],
        '_metrics': metrics,
    }


def run_benchmark(
    steps: int = 120,
    seed: int = 7,
    scenario: str = 'rush',
    shielded: bool = DEFAULT_SHIELDED,
) -> list[dict]:
    return [
        _single_run(name, steps=steps, seed=seed, scenario=scenario, shielded=shielded)
        for name in controller_names()
    ]


def run_benchmark_suite(
    steps: int = 180,
    seeds: list[int] | None = None,
    scenarios: list[str] | None = None,
    shielded: bool = DEFAULT_SHIELDED,
) -> dict:
    """Robust controller comparison across demand and disturbance cases."""
    seeds = seeds or [3, 7, 11, 19, 29]
    scenarios = scenarios or ['normal', 'rush', 'accident', 'rush-accident']
    raw: list[dict] = []

    for scenario in scenarios:
        base_scenario = 'rush' if scenario.startswith('rush') else 'normal'
        event = 'accident' if 'accident' in scenario else None
        for seed in seeds:
            for name in controller_names():
                raw.append(_single_run(
                    name,
                    steps=steps,
                    seed=seed,
                    scenario=base_scenario,
                    event=event,
                    event_tick=max(10, steps // 4),
                    shielded=shielded,
                ))

    def avg(rows: list[dict], key: str) -> float:
        return round(mean([r[key] for r in rows]), 3)

    summary = []
    for name in controller_names():
        rows = [r for r in raw if r['controller'] == name]
        queues = [r['average_network_queue'] for r in rows]
        summary.append({
            'controller': name,
            'runs': len(rows),
            'mean_average_queue': round(mean(queues), 3),
            'queue_stddev': round(pstdev(queues), 3),
            'mean_throughput': avg(rows, 'throughput'),
            'mean_peak_queue': avg(rows, 'peak_queue'),
            'mean_phase_switches': avg(rows, 'phase_switches'),
            'mean_vehicle_delay': avg(rows, 'mean_vehicle_delay'),
            'mean_p95_vehicle_delay': avg(rows, 'p95_vehicle_delay'),
            'mean_worst_approach_wait': avg(rows, 'worst_approach_wait'),
            'mean_person_delay': avg(rows, 'mean_person_delay'),
            'mean_bus_delay': avg(rows, 'mean_bus_delay'),
            'mean_pedestrian_delay': avg(rows, 'mean_pedestrian_delay'),
            'mean_blocked_arrivals': avg(rows, 'blocked_arrivals'),
            'mean_demand_served_pct': avg(rows, 'demand_served_pct'),
            'mean_co2_kg': avg(rows, 'co2_kg'),
        })

    fixed = next(r for r in summary if r['controller'] == BASELINE)
    for row in summary:
        row['queue_improvement_vs_fixed_pct'] = round(
            100.0 * (fixed['mean_average_queue'] - row['mean_average_queue'])
            / max(1e-9, fixed['mean_average_queue']), 2
        )
        row['throughput_improvement_vs_fixed_pct'] = round(
            100.0 * (row['mean_throughput'] - fixed['mean_throughput'])
            / max(1e-9, fixed['mean_throughput']), 2
        )
        row['p95_improvement_vs_fixed_pct'] = round(
            100.0 * (fixed['mean_p95_vehicle_delay'] - row['mean_p95_vehicle_delay'])
            / max(1e-9, fixed['mean_p95_vehicle_delay']), 2
        )

    # Ranking on average queue alone is not safe. Once demand exceeds capacity,
    # an approach that is held at red fills up and then *refuses* arrivals, so a
    # controller can post a shorter queue simply by turning more traffic away at
    # the boundary. Measured on this network, plain fixed-time blocks about 100
    # more vehicles per run than the coordinated controller and looks better for
    # it. So demand actually served is the first key, and queue only breaks ties
    # among controllers that served the same share of demand. At normal demand
    # nothing is blocked and this reduces to the old queue ranking.
    ranking = sorted(summary, key=lambda r: (
        -round(r['mean_demand_served_pct'], 1),
        r['mean_average_queue'],
        -r['mean_throughput'],
    ))
    best = ranking[0]['controller']

    # City-facing translation of the winner against the fixed-time baseline,
    # averaged over every run so it is not cherry-picked from one seed.
    def pooled(name: str) -> dict:
        rows = [r['_metrics'] for r in raw if r['controller'] == name]
        keys = (
            'total_vehicle_wait_ticks', 'total_bus_wait_ticks',
            'total_person_wait_ticks',
        )
        return {k: sum(m.get(k, 0) for m in rows) / len(rows) for k in keys}

    impact = compare_impact(pooled(BASELINE), pooled(best), steps=steps)

    for row in summary:
        row.pop('_metrics', None)
    for row in raw:
        row.pop('_metrics', None)

    return {
        'steps_per_run': steps,
        'seeds': seeds,
        'scenarios': scenarios,
        'shielded': shielded,
        'summary': ranking,
        'raw': raw,
        'best_controller': best,
        'impact_vs_fixed_time': impact,
        'note': 'Mock-engine development benchmark only; final SIH claims must be regenerated in SUMO/TraCI.',
    }
