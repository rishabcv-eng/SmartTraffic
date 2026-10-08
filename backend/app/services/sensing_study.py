"""The blind-detector demonstration, as a trace you can plot.

The sensing result is hard to believe from a table and obvious from a graph: a
detector reports zero for the rest of the run, one controller believes it and
lets a queue build behind it, the other refuses to and keeps the road moving.

Returns the tick-by-tick truth alongside what the detector claimed, so the gap
between the two is the whole story.
"""

from __future__ import annotations

from statistics import mean

from app.controllers.registry import build
from app.simulation.mock_engine import MockTrafficEngine

#: Approaches whose detectors are killed partway through.
BLIND = (('J1', 'north'), ('J3', 'south'))

COMPARED = ('coordinated-pressure-v1', 'belief-pressure-v1')

LABELS = {
    'coordinated-pressure-v1': 'Trusts the detector',
    'belief-pressure-v1': 'Keeps a belief (ours)',
}


def _trace(controller: str, seed: int, fail_at: int, steps: int,
           noise: float, shielded: bool) -> dict:
    engine = MockTrafficEngine()
    engine.sensor_noise = noise
    engine.reset(scenario='rush', seed=seed)
    ctrl = build(controller, shielded=shielded)

    truth: list[int] = []
    reported: list[int] = []
    served_blind = 0

    for tick in range(steps):
        if tick == fail_at:
            for jid, direction in BLIND:
                engine.inject_fault('detector-dropout', jid, direction)

        snapshot = engine.snapshot()
        actions = ctrl.choose_phases(snapshot)

        # Was the blinded approach actually given green this tick?
        for jid, direction in BLIND:
            phase = actions.get(jid)
            if phase and direction in (('north', 'south') if phase == 'NS' else ('east', 'west')):
                served_blind += 1
                break

        truth.append(sum(len(engine.lanes[k]) for k in BLIND))
        reported.append(sum(getattr(j, d) for j in snapshot.junctions
                            for jid, d in BLIND if j.id == jid))
        engine.step(actions)

    metrics = engine.snapshot().metrics
    return {
        'controller': controller,
        'label': LABELS[controller],
        'truth': truth,
        'reported': reported,
        'green_given_to_blind_approach': served_blind,
        'final_hidden_queue': truth[-1],
        'served_vehicles': metrics['served_vehicles'],
        'p95_vehicle_delay': metrics['p95_vehicle_delay'],
    }


#: The plotted run. Chosen as the seed whose outcome sits closest to the median
#: across the seed set, not the one that flatters the result -- seed 3 shows a
#: gap of 22 vehicles and seed 29 goes the other way by 4. The pooled figures
#: beneath the chart are what the claim rests on.
REPRESENTATIVE_SEED = 19


def compare_sensing(
    seed: int = REPRESENTATIVE_SEED,
    steps: int = 160,
    fail_at: int = 40,
    noise: float = 0.14,
    shielded: bool = False,
    seeds: list[int] | None = None,
) -> dict:
    """Run both controllers through the same detector failure.

    ``shielded=False`` by default on purpose: the safety shield's maximum green
    already caps starvation, so with it on both controllers look fine and the
    comparison shows nothing. Unshielded isolates what the belief layer itself
    contributes, which is the honest way to present it.
    """
    steps = max(60, min(steps, 400))
    fail_at = max(5, min(fail_at, steps - 20))

    traces = [_trace(name, seed, fail_at, steps, noise, shielded) for name in COMPARED]

    # A spread of seeds behind the single plotted run, so the headline is not
    # one lucky trace.
    pooled = {}
    for name in COMPARED:
        runs = [_trace(name, s, fail_at, steps, noise, shielded)
                for s in (seeds or [3, 7, 11, 19, 29])]
        pooled[name] = {
            'mean_final_hidden_queue': round(mean(r['final_hidden_queue'] for r in runs), 1),
            'mean_green_to_blind': round(mean(r['green_given_to_blind_approach'] for r in runs), 1),
            'mean_served': round(mean(r['served_vehicles'] for r in runs), 1),
            'seeds': len(runs),
        }

    naive, belief = pooled[COMPARED[0]], pooled[COMPARED[1]]
    reduction = (100.0 * (naive['mean_final_hidden_queue'] - belief['mean_final_hidden_queue'])
                 / max(1e-9, naive['mean_final_hidden_queue']))

    return {
        'setup': {
            'blind_approaches': [f'{j}-{d}' for j, d in BLIND],
            'fail_at_tick': fail_at,
            'steps': steps,
            'sensor_noise': noise,
            'shielded': shielded,
            'seed_plotted': seed,
        },
        'traces': traces,
        'pooled': pooled,
        'headline': {
            'hidden_queue_reduction_pct': round(reduction, 1),
            'naive_hidden_queue': naive['mean_final_hidden_queue'],
            'belief_hidden_queue': belief['mean_final_hidden_queue'],
            'throughput_cost': round(naive['mean_served'] - belief['mean_served'], 1),
        },
        'reading': (
            'After the detector dies it reports zero for the rest of the run. One '
            'controller believes it; the other treats an approach it cannot see as '
            'possibly long and keeps serving it.'
        ),
        'caveat': (
            'Shown unshielded. With the safety shield on, maximum green already caps '
            'the starvation and both controllers stay near zero -- the belief layer '
            'reaches the same place by inference rather than by timeout.'
        ),
    }
