"""Run the mixed-fleet comparison live, so the novelty is demonstrable.

The heterogeneous-discharge result existed only in a document and a test. That
is enough to be true and not enough to be shown. This runs the same comparison
on demand, with the same paired confidence intervals, so the claim can be put
on screen and re-run in front of whoever is asking.
"""

from __future__ import annotations

from math import sqrt
from statistics import mean, stdev

from app.controllers.registry import build
from app.simulation.mock_engine import MockTrafficEngine

#: A two-wheeler feeder road meeting a bus arterial. The contrast is the whole
#: point: a systematic mis-measurement cancels out when both approaches carry
#: the same traffic, and only changes a decision when they differ.
TW_HEAVY = {'two-wheeler': 0.78, 'auto': 0.12, 'car': 0.09, 'bus': 0.01}
CAR_HEAVY = {'car': 0.62, 'bus': 0.16, 'auto': 0.14, 'two-wheeler': 0.08}

COMPARED = ('pcu-timed-v1', 'heterogeneous-timed-v1', 'person-seconds-v1')

LABELS = {
    'pcu-timed-v1': 'Static PCU (deployed today)',
    'heterogeneous-timed-v1': 'Discharge-seconds (efficiency only)',
    'person-seconds-v1': 'People per second of green (ours)',
}

TRACKED = {
    'served_people': 'people moved',
    'served_vehicles': 'vehicles moved',
    'p95_vehicle_delay': '95th percentile delay',
    'worst_approach_wait': 'worst approach wait',
}


def _run(controller: str, seed: int, demand: float, contrast: bool, steps: int) -> dict:
    engine = MockTrafficEngine()
    if contrast:
        for jid in MockTrafficEngine.JUNCTION_IDS:
            for d in ('north', 'south'):
                engine.approach_mix[(jid, d)] = TW_HEAVY
            for d in ('east', 'west'):
                engine.approach_mix[(jid, d)] = CAR_HEAVY
    engine.reset(scenario='rush', seed=seed)
    engine.arrival_multiplier = demand

    controller_obj = build(controller, shielded=False)
    for _ in range(steps):
        engine.step(controller_obj.choose_phases(engine.snapshot()))
    return engine.snapshot().metrics


def compare_fleet(
    seeds: list[int] | None = None,
    demand_multiplier: float = 7.0,
    contrast: bool = True,
    steps: int = 200,
) -> dict:
    """Three ways of measuring pressure, on identical traffic.

    ``contrast=False`` gives every approach the same mix, which is the control
    condition: the effect should vanish, and if it does not, the explanation in
    ``docs/HETEROGENEOUS_FLOW.md`` is wrong.
    """
    seeds = seeds or [3, 7, 11, 19, 29, 37, 41, 53]
    steps = max(50, min(steps, 400))

    runs = {
        name: [_run(name, s, demand_multiplier, contrast, steps) for s in seeds]
        for name in COMPARED
    }

    rows = []
    for name in COMPARED:
        metrics = runs[name]
        rows.append({
            'controller': name,
            'label': LABELS[name],
            **{key: round(mean(m[key] for m in metrics), 1) for key in TRACKED},
        })

    baseline = runs['pcu-timed-v1']
    deltas = []
    for name in COMPARED[1:]:
        entry = {'controller': name, 'label': LABELS[name], 'metrics': {}}
        for key in TRACKED:
            paired = [b[key] - a[key] for a, b in zip(baseline, runs[name])]
            m = mean(paired)
            ci = 1.96 * stdev(paired) / sqrt(len(paired)) if len(paired) > 1 else 0.0
            entry['metrics'][key] = {
                'mean': round(m, 1),
                'ci': round(ci, 1),
                'significant': abs(m) > ci > 0,
            }
        deltas.append(entry)

    return {
        'question': {
            'seeds': seeds,
            'demand_multiplier': demand_multiplier,
            'contrasting_mixes': contrast,
            'steps': steps,
            'north_south_mix': TW_HEAVY if contrast else 'default',
            'east_west_mix': CAR_HEAVY if contrast else 'default',
        },
        'rows': rows,
        'vs_static_pcu': deltas,
        'tracked': TRACKED,
        'reading': (
            'Differences are against the static-PCU controller, which is what an '
            'adaptive system deployed in an Indian city does today. With every '
            'approach on the same mix the effect should disappear: the bias '
            'applies equally to both sides of the comparison and cancels.'
            if contrast else
            'Control condition. Every approach carries the same mix, so the '
            'measurement bias cancels and no significant effect should appear.'
        ),
        'caveat': (
            'Discharge parameters are centre estimates, not measurements from a '
            'real junction. See docs/HETEROGENEOUS_FLOW.md.'
        ),
    }
