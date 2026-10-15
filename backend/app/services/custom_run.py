"""Run the simulation on numbers the user types in.

Every control on the page was a preset -- a named traffic pattern, a named
demand profile. There was nowhere to say "put 1400 vehicles an hour on the north
road, make 60% of them scooters, and show me what happens". That is the first
thing anyone wants to do with a traffic model, and it was missing.

This takes raw demand per approach and a fleet mix, applies them to the engine,
and runs whichever controllers are asked for on identical traffic.
"""

from __future__ import annotations

from app.controllers.registry import CONTROLLERS, build
from app.services.calibration import BASE_VEHICLES_PER_HOUR
from app.simulation.mock_engine import MockTrafficEngine

#: The four compass directions a user thinks in, mapped onto every approach
#: that actually receives traffic from outside the network.
EXTERNAL = MockTrafficEngine.EXTERNAL_APPROACHES

VEHICLE_KINDS = ('two-wheeler', 'car', 'auto', 'bus')

#: Sensible starting point: an Indian urban arterial at moderate demand.
DEFAULT_ARRIVALS = {'north': 1200, 'south': 900, 'east': 1400, 'west': 1000}
DEFAULT_MIX = {'two-wheeler': 45, 'car': 33, 'auto': 18, 'bus': 4}


def _normalise_mix(mix: dict[str, float]) -> dict[str, float]:
    """Percentages to fractions, tolerating anything that does not sum to 100."""
    clean = {k: max(0.0, float(mix.get(k, 0))) for k in VEHICLE_KINDS}
    total = sum(clean.values())
    if total <= 0:
        return {k: v / 100.0 for k, v in DEFAULT_MIX.items()}
    return {k: v / total for k, v in clean.items()}


def run_custom(
    arrivals: dict[str, float] | None = None,
    mix: dict[str, float] | None = None,
    controllers: list[str] | None = None,
    steps: int = 180,
    seed: int = 7,
    shielded: bool = True,
) -> dict:
    """Run the given demand through each controller on identical traffic.

    ``arrivals`` is vehicles per hour per compass direction, which is the unit a
    traffic count is actually collected in. ``mix`` is percentages by class.
    """
    arrivals = {**DEFAULT_ARRIVALS, **(arrivals or {})}
    fractions = _normalise_mix(mix or DEFAULT_MIX)
    controllers = controllers or ['fixed-time', 'person-seconds-v1']
    controllers = [c for c in controllers if c in CONTROLLERS][:4] or ['fixed-time']
    steps = max(40, min(int(steps), 600))

    # Vehicles per hour -> the engine's per-approach demand multiplier.
    scales: dict[tuple[str, str], float] = {}
    for jid, directions in EXTERNAL.items():
        for d in directions:
            vph = max(0.0, float(arrivals.get(d, 0)))
            scales[(jid, d)] = vph / BASE_VEHICLES_PER_HOUR

    results = []
    for name in controllers:
        engine = MockTrafficEngine()
        # Composition is configuration: set before reset so the standing queues
        # are built from the same mix as the arrivals that follow.
        for jid, directions in EXTERNAL.items():
            for d in directions:
                engine.approach_mix[(jid, d)] = dict(fractions)
        engine.reset(scenario='normal', seed=seed)
        engine.demand_scale = dict(scales)
        engine.arrival_multiplier = 1.0

        controller = build(name, shielded=shielded)
        for _ in range(steps):
            engine.step(controller.choose_phases(engine.snapshot()))

        snap = engine.snapshot()
        m = snap.metrics
        results.append({
            'controller': name,
            'vehicles_served': m['served_vehicles'],
            'people_moved': round(m['served_people']),
            'mean_delay': m['mean_vehicle_delay'],
            'p95_delay': m['p95_vehicle_delay'],
            'worst_approach_wait': m['worst_approach_wait'],
            'blocked_arrivals': m['blocked_arrivals'],
            'final_queue': sum(j.queue for j in snap.junctions),
            'queues': {j.id: {'north': j.north, 'south': j.south,
                              'east': j.east, 'west': j.west}
                       for j in snap.junctions},
        })

    baseline = results[0]
    for row in results[1:]:
        row['vs_first'] = {
            'people_moved': round(row['people_moved'] - baseline['people_moved']),
            'vehicles_served': row['vehicles_served'] - baseline['vehicles_served'],
            'p95_delay': round(row['p95_delay'] - baseline['p95_delay'], 1),
        }

    total_vph = sum(max(0.0, float(arrivals.get(d, 0))) for d in ('north', 'south', 'east', 'west'))
    return {
        'input': {
            'arrivals_vph': {d: round(float(arrivals.get(d, 0))) for d in
                             ('north', 'south', 'east', 'west')},
            'mix_pct': {k: round(v * 100, 1) for k, v in fractions.items()},
            'steps': steps,
            'seed': seed,
            'shielded': shielded,
            'total_demand_vph': round(total_vph),
            'simulated_minutes': round(steps * 5 / 60.0, 1),
        },
        'results': results,
        'note': (
            'Both controllers see identical traffic: the same seed, the same demand '
            'and the same fleet mix. Any difference is the signal policy.'
        ),
    }
