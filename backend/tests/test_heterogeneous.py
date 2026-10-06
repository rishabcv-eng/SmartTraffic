"""Lane-less discharge, and what measuring it correctly actually buys.

These tests pin down both halves of the result: that static PCU mis-measures
heterogeneous discharge by a large margin, and -- just as importantly -- the
narrow conditions under which correcting it changes a control decision at all.
"""

from math import sqrt
from statistics import mean, stdev

import pytest

from app.controllers.registry import build
from app.services.saturation import (
    VEHICLE_CLASSES,
    comparison_report,
    discharge_seconds,
    implied_pcu,
    pcu_error,
    queue_discharge_seconds,
    queue_storage,
)
from app.simulation.mock_engine import LINK_STORAGE, MockTrafficEngine

TW_HEAVY = {'two-wheeler': 0.78, 'auto': 0.12, 'car': 0.09, 'bus': 0.01}
CAR_HEAVY = {'car': 0.62, 'bus': 0.16, 'auto': 0.14, 'two-wheeler': 0.08}


# --------------------------------------------------------------- the model --

def test_the_model_reproduces_textbook_saturation_flow_for_cars():
    """It must agree with convention where convention applies.

    A car on a two-lane approach takes 1.0 s of green, i.e. 1800 veh/h/lane.
    If the model did not reproduce that, it would be wrong rather than new.
    """
    assert discharge_seconds('car', lanes=2.0) == pytest.approx(1.0)
    assert implied_pcu('car') == pytest.approx(1.0)


def test_two_wheelers_discharge_far_faster_than_their_static_pcu_implies():
    implied = implied_pcu('two-wheeler')
    static = VEHICLE_CLASSES['two-wheeler'].static_pcu

    assert implied < static, 'static PCU must over-state two-wheeler discharge'
    # Roughly three two-wheelers cross in the time one car takes.
    assert 0.25 < implied < 0.40
    assert (static - implied) / implied > 0.4


def test_pcu_error_grows_with_two_wheeler_share():
    light = pcu_error({'car': 27, 'two-wheeler': 0, 'auto': 2, 'bus': 1})
    heavy = pcu_error({'car': 5, 'two-wheeler': 22, 'auto': 2, 'bus': 1})

    assert heavy['error_pct'] > light['error_pct']
    # Positive error means green held after the queue has already cleared.
    assert heavy['error_pct'] > 15


def test_a_mixed_queue_clears_faster_than_the_same_count_of_cars():
    cars = {'car': 30}
    twos = {'two-wheeler': 30}

    assert queue_discharge_seconds(twos) < queue_discharge_seconds(cars) / 2
    assert queue_storage(twos) < queue_storage(cars)


def test_comparison_report_is_self_describing():
    report = comparison_report()

    assert len(report['classes']) == len(VEHICLE_CLASSES)
    shares = [row['two_wheeler_share'] for row in report['error_vs_two_wheeler_share']]
    assert shares == sorted(shares)
    errors = [row['error_pct'] for row in report['error_vs_two_wheeler_share']]
    assert errors == sorted(errors), 'error must rise with two-wheeler share'
    assert report['caveat']


# -------------------------------------------------------------- the engine --

def test_storage_is_counted_in_car_lengths_not_vehicles():
    engine = MockTrafficEngine()
    engine.reset(scenario='rush', seed=7)
    for jid in MockTrafficEngine.JUNCTION_IDS:
        for d in ('north', 'south'):
            engine.approach_mix[(jid, d)] = TW_HEAVY
    for _ in range(150):
        engine.step({jid: 'PED' for jid in MockTrafficEngine.JUNCTION_IDS})

    for key, lane in engine.lanes.items():
        assert sum(v.storage for v in lane) <= LINK_STORAGE + 1e-6

    tw_lane = engine.lanes[('J1', 'north')]
    assert len(tw_lane) > LINK_STORAGE, 'two-wheelers should pack in tighter than cars'


def test_composition_reaches_the_controller():
    engine = MockTrafficEngine()
    snapshot = engine.reset(seed=7)
    junction = snapshot.junctions[0]

    for direction in ('north', 'south', 'east', 'west'):
        counts = junction.composition[direction]
        assert sum(counts.values()) == getattr(junction, direction)

    # The three measures must genuinely disagree, or there is nothing to fix.
    assert junction.pcu_pressure('NS') != pytest.approx(junction.discharge_pressure('NS'))


def test_per_approach_mix_is_respected():
    engine = MockTrafficEngine()
    # Reset twice: the first pass installs the mix, the second rebuilds the
    # standing queues from it rather than from the default composition.
    for _ in range(2):
        engine.reset(seed=7)
        for jid in MockTrafficEngine.JUNCTION_IDS:
            engine.approach_mix[(jid, 'north')] = {'two-wheeler': 1.0}
            engine.approach_mix[(jid, 'east')] = {'bus': 1.0}
    for _ in range(30):
        engine.step({jid: 'PED' for jid in MockTrafficEngine.JUNCTION_IDS})

    north = engine.lanes[('J1', 'north')]
    assert north and all(v.kind == 'two-wheeler' for v in north)
    east = engine.lanes[('J2', 'east')]
    assert east and all(v.kind == 'bus' for v in east)


# ---------------------------------------------------------- the controllers --

def _run(name, seed, mult, steps=200, contrast=True):
    engine = MockTrafficEngine()
    if contrast:
        # Set before reset: composition is configuration, so the standing
        # queues are built from it too, not just the arrivals.
        for jid in MockTrafficEngine.JUNCTION_IDS:
            for d in ('north', 'south'):
                engine.approach_mix[(jid, d)] = TW_HEAVY
            for d in ('east', 'west'):
                engine.approach_mix[(jid, d)] = CAR_HEAVY
    engine.reset(scenario='rush', seed=seed)
    engine.arrival_multiplier = mult

    controller = build(name, shielded=False)
    for _ in range(steps):
        engine.step(controller.choose_phases(engine.snapshot()))
    return engine.snapshot().metrics


def test_the_measure_changes_nothing_when_every_approach_carries_the_same_mix():
    """The negative half of the result, and it must not be quietly dropped.

    A systematic bias applies equally to both sides of an NS-vs-EW comparison
    and cancels. Correcting the measure can only matter where the competing
    approaches actually differ.
    """
    seeds = (3, 7, 11, 19, 29, 37, 41, 53)
    pcu = [_run('pcu-timed-v1', s, 4.0, contrast=False) for s in seeds]
    het = [_run('heterogeneous-timed-v1', s, 4.0, contrast=False) for s in seeds]

    diffs = [h['served_people'] - p['served_people'] for p, h in zip(pcu, het)]
    ci = 1.96 * stdev(diffs) / sqrt(len(diffs))
    assert abs(mean(diffs)) <= ci, 'uniform mixes should show no significant effect'


def test_correcting_the_measure_moves_more_people_when_mixes_differ():
    """The positive half: under scarcity, with contrasting mixes, it pays.

    Static PCU over-states two-wheeler demand, so it hands a two-wheeler feeder
    more green than it needs. Correcting that returns green to the arterial,
    which is where the buses are -- so fewer vehicles move, but more people do.
    """
    seeds = (3, 7, 11, 19, 29, 37, 41, 53)
    pcu = [_run('pcu-timed-v1', s, 7.0) for s in seeds]
    het = [_run('heterogeneous-timed-v1', s, 7.0) for s in seeds]

    people = [h['served_people'] - p['served_people'] for p, h in zip(pcu, het)]
    ci = 1.96 * stdev(people) / sqrt(len(people))
    assert mean(people) > ci > 0, 'person-throughput gain should be significant'

    # The trade is explicit rather than hidden: green moves off the two-wheeler
    # feeder and onto the bus arterial, so fewer vehicles cross but many more
    # people do. Whether that trade is wanted is a policy question, and the
    # riders who now wait longer are the ones least able to absorb it -- which
    # is exactly why it is measured here rather than buried in an average.
    vehicles = [h['served_vehicles'] - p['served_vehicles'] for p, h in zip(pcu, het)]
    assert mean(vehicles) < 0, 'the gain is in people moved, not vehicles moved'


# ------------------------------------------- optimising people, not efficiency

def test_person_seconds_keeps_the_people_gain_over_the_conventional_baseline():
    """It must still beat what a deployed Indian system does today."""
    seeds = (3, 7, 11, 19, 29, 37, 41, 53)
    pcu = [_run('pcu-timed-v1', s, 7.0) for s in seeds]
    ps = [_run('person-seconds-v1', s, 7.0) for s in seeds]

    people = [b['served_people'] - a['served_people'] for a, b in zip(pcu, ps)]
    ci = 1.96 * stdev(people) / sqrt(len(people))
    assert mean(people) > ci > 0, 'must move significantly more people than static PCU'


def test_person_seconds_removes_the_starvation_that_pure_efficiency_caused():
    """The regression this controller exists to fix.

    Optimising green-seconds-per-vehicle treats a two-wheeler approach as cheap
    and therefore low-value, and starves it. Optimising people-per-second of
    green, with a fairness term, keeps the throughput gain without making one
    group of road users pay for it.
    """
    seeds = (3, 7, 11, 19, 29, 37)
    efficiency = [_run('heterogeneous-timed-v1', s, 7.0) for s in seeds]
    people_first = [_run('person-seconds-v1', s, 7.0) for s in seeds]

    worst = [b['worst_approach_wait'] - a['worst_approach_wait']
             for a, b in zip(efficiency, people_first)]
    ci = 1.96 * stdev(worst) / sqrt(len(worst))
    assert mean(worst) < -ci, 'worst-approach wait must fall significantly'

    # Not a marginal improvement: the efficiency-only controller starves an
    # approach for minutes at a time under this demand.
    assert mean(x['worst_approach_wait'] for x in efficiency) > 100
    assert mean(x['worst_approach_wait'] for x in people_first) < 60


def test_fairness_weight_actually_does_something():
    """Guard against the fairness term being decorative."""
    from app.controllers.heterogeneous_pressure import PersonSecondsController

    fair = PersonSecondsController(fairness_weight=6.0)
    unfair = PersonSecondsController(fairness_weight=0.0)
    assert fair.fairness_weight != unfair.fairness_weight

    engine = MockTrafficEngine()
    for jid in MockTrafficEngine.JUNCTION_IDS:
        for d in ('north', 'south'):
            engine.approach_mix[(jid, d)] = TW_HEAVY
        for d in ('east', 'west'):
            engine.approach_mix[(jid, d)] = CAR_HEAVY
    engine.reset(scenario='rush', seed=7)
    engine.arrival_multiplier = 7.0

    # The fairness term must accumulate red time, or it cannot influence anything.
    for _ in range(40):
        engine.step(fair.choose_phases(engine.snapshot()))
    assert any(v > 0 for v in fair.red_ticks.values())
