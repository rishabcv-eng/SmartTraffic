"""Control under sensing uncertainty.

Two halves, and the second matters as much as the first: acting on a belief
instead of a reading rescues the queue hidden behind a broken detector, and it
costs throughput when the detectors are fine. A controller that only ever
helped would mean the experiment was not measuring anything.
"""

from math import sqrt
from statistics import mean, stdev

import pytest

from app.controllers.belief_pressure import BeliefPressureController
from app.controllers.registry import build
from app.simulation.mock_engine import MockTrafficEngine

SEEDS = (3, 7, 11, 19, 29, 37, 41, 53)


def run(controller, seed, *, noise=0.14, dropout=False, shielded=False, steps=200):
    engine = MockTrafficEngine()
    engine.sensor_noise = noise
    engine.reset(scenario='rush', seed=seed)
    ctrl = build(controller, shielded=shielded)
    for i in range(steps):
        if dropout and i == 40:
            engine.inject_fault('detector-dropout', 'J1', 'north')
            engine.inject_fault('detector-dropout', 'J3', 'south')
        engine.step(ctrl.choose_phases(engine.snapshot()))
    metrics = engine.snapshot().metrics
    metrics = dict(metrics)
    # The queue standing behind a detector that is reporting zero.
    metrics['blind_queue'] = (len(engine.lanes[('J1', 'north')])
                              + len(engine.lanes[('J3', 'south')]))
    return metrics


def paired(a, b, key):
    d = [y[key] - x[key] for x, y in zip(a, b)]
    m = mean(d)
    ci = 1.96 * stdev(d) / sqrt(len(d)) if len(d) > 1 else 0.0
    return m, ci


# ----------------------------------------------------------- sensing model --

def test_perfect_sensing_is_the_default_and_reports_full_confidence():
    """Noise is opt-in, so every existing result is untouched by this work."""
    engine = MockTrafficEngine()
    engine.reset(scenario='rush', seed=7)
    junction = engine.snapshot().junctions[0]

    assert engine.sensor_noise == 0.0
    assert set(junction.confidence.values()) == {1.0}
    for d in ('north', 'south', 'east', 'west'):
        assert getattr(junction, d) == len(engine.lanes[('J1', d)])


def test_noise_corrupts_the_reading_without_touching_the_traffic():
    """Sensing draws from its own stream, or a paired comparison is worthless."""
    clean = MockTrafficEngine(); clean.reset(scenario='rush', seed=7)
    noisy = MockTrafficEngine(); noisy.sensor_noise = 0.2
    noisy.reset(scenario='rush', seed=7)

    for _ in range(25):
        clean.step({j: 'NS' for j in MockTrafficEngine.JUNCTION_IDS})
        noisy.step({j: 'NS' for j in MockTrafficEngine.JUNCTION_IDS})

    # The physical queues must be identical; only the readings differ.
    for key in clean.lanes:
        assert len(clean.lanes[key]) == len(noisy.lanes[key]), key

    readings = [getattr(j, d) for j in noisy.snapshot().junctions
                for d in ('north', 'south', 'east', 'west')]
    truth = [len(noisy.lanes[(j.id, d)]) for j in noisy.snapshot().junctions
             for d in ('north', 'south', 'east', 'west')]
    assert readings != truth, 'noise should actually corrupt something'


def test_confidence_falls_with_weather_and_with_two_wheelers():
    engine = MockTrafficEngine()
    engine.sensor_noise = 0.15
    engine.approach_mix[('J1', 'north')] = {'two-wheeler': 1.0}
    engine.approach_mix[('J1', 'west')] = {'bus': 1.0}
    engine.reset(scenario='rush', seed=7)

    tw = engine.sensing_quality('J1', 'north')
    bus = engine.sensing_quality('J1', 'west')
    assert tw < bus, 'overlapping two-wheelers are harder to count than buses'

    engine.set_weather('fog')
    assert engine.sensing_quality('J1', 'north') < tw


def test_a_dead_detector_reports_no_confidence():
    engine = MockTrafficEngine()
    engine.reset(scenario='rush', seed=7)
    engine.inject_fault('detector-dropout', 'J2', 'east')

    assert engine.sensing_quality('J2', 'east') == 0.0
    assert next(j for j in engine.snapshot().junctions if j.id == 'J2').east == 0


# --------------------------------------------------------- the belief layer --

def test_belief_refuses_to_trust_a_dead_detector():
    engine = MockTrafficEngine()
    engine.sensor_noise = 0.14
    engine.reset(scenario='rush', seed=7)
    ctrl = BeliefPressureController()

    for i in range(60):
        if i == 20:
            engine.inject_fault('detector-dropout', 'J1', 'north')
        engine.step(ctrl.choose_phases(engine.snapshot()))

    rows = {r['approach']: r for r in ctrl.explain(engine.snapshot())['approaches']}
    blind = rows['J1-north']
    assert blind['confidence'] == 0.0
    assert blind['reading'] == 0
    # The point of the whole controller: it acts on more than the zero it sees.
    assert blind['acts_on'] > blind['reading']


def test_it_rescues_the_queue_behind_a_broken_detector():
    """The result this controller exists for, measured without the shield.

    The safety shield's maximum green already caps starvation, so with it on
    the benefit is mostly hidden. Unshielded isolates what the belief layer
    itself contributes.
    """
    naive = [run('coordinated-pressure-v1', s, dropout=True) for s in SEEDS]
    belief = [run('belief-pressure-v1', s, dropout=True) for s in SEEDS]

    m, ci = paired(naive, belief, 'blind_queue')
    assert m < -ci, 'hidden queue should fall significantly'

    naive_queue = mean(x['blind_queue'] for x in naive)
    belief_queue = mean(x['blind_queue'] for x in belief)
    assert belief_queue < naive_queue * 0.6, (
        f'expected a substantial reduction, got {naive_queue:.1f} -> {belief_queue:.1f}')


def test_the_caution_margin_costs_throughput_when_sensors_are_healthy():
    """The other half. Hedging against bad data is not free.

    Measured shielded, which is the configuration a city would deploy. The
    cost is real there; unshielded with perfect sensors it is inside the noise,
    which is itself worth knowing and is why the condition is stated.
    """
    naive = [run('coordinated-pressure-v1', s, noise=0.0, shielded=True) for s in SEEDS]
    belief = [run('belief-pressure-v1', s, noise=0.0, shielded=True) for s in SEEDS]

    m, ci = paired(naive, belief, 'served_vehicles')
    assert m < -ci, 'belief control should measurably cost throughput here'
    # Small, though -- it should be a margin, not a tax.
    assert abs(m) / mean(x['served_vehicles'] for x in naive) < 0.03


def test_caution_of_zero_collapses_to_acting_on_the_estimate():
    engine = MockTrafficEngine()
    engine.reset(scenario='rush', seed=7)
    ctrl = BeliefPressureController(caution=0.0)
    for _ in range(10):
        engine.step(ctrl.choose_phases(engine.snapshot()))

    for row in ctrl.explain(engine.snapshot())['approaches']:
        assert row['acts_on'] == pytest.approx(row['belief'], abs=1e-6)
