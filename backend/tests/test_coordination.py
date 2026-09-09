"""Link storage, spillback, and the coordinated controller that answers them.

The benchmark originally showed every adaptive controller losing to a fixed
clock under saturation. Two things were wrong: the engine had unbounded link
storage, and the controllers optimised each junction independently, destroying
the progression a fixed clock gets for free by switching everything in unison.
These tests pin down both fixes.
"""

from statistics import mean

from app.controllers.coordinated_pressure import CoordinatedPressureController
from app.controllers.gated_pressure import GatedPressureController
from app.controllers.safety import SafetyShield
from app.services.scenario import ScenarioConfig, simulate
from app.simulation.mock_engine import LINK_STORAGE, MockTrafficEngine

SEEDS = (3, 7, 11, 19, 29)


def pooled(controller: str, scenario: str, key, steps: int = 180):
    runs = [
        simulate(ScenarioConfig(controller=controller, steps=steps, seed=seed, scenario=scenario))
        for seed in SEEDS
    ]
    return mean(key(r) for r in runs)


# ------------------------------------------------------------- link storage

def test_no_approach_can_exceed_its_physical_storage():
    engine = MockTrafficEngine()
    engine.reset(scenario='rush', seed=7)
    # Hold a pedestrian phase so nothing is ever served and every lane fills.
    for _ in range(200):
        engine.step({jid: 'PED' for jid in MockTrafficEngine.JUNCTION_IDS})

    assert max(len(lane) for lane in engine.lanes.values()) <= LINK_STORAGE


def test_demand_that_cannot_enter_is_counted_not_dropped():
    engine = MockTrafficEngine()
    engine.reset(scenario='rush', seed=7)
    for _ in range(200):
        engine.step({jid: 'PED' for jid in MockTrafficEngine.JUNCTION_IDS})

    metrics = engine.snapshot().metrics
    assert metrics['blocked_arrivals'] > 0
    # Offered demand is always at least what physically entered.
    assert sum(engine.arrivals_seen.values()) >= sum(len(l) for l in engine.lanes.values())


def test_a_full_downstream_link_blocks_the_upstream_movement():
    engine = MockTrafficEngine()
    engine.reset(seed=7)
    # J1-west discharges into J2-west. Fill the receiving link completely.
    from collections import deque
    from app.simulation.mock_engine import Vehicle
    engine.lanes[('J2', 'west')] = deque(
        Vehicle(arrival_tick=0) for _ in range(LINK_STORAGE)
    )
    held = len(engine.lanes[('J1', 'west')])

    engine.step({'J1': 'EW', 'J2': 'PED', 'J3': 'PED', 'J4': 'PED'})

    # Green was given, but the vehicles physically could not move.
    assert len(engine.lanes[('J1', 'west')]) >= held
    assert engine.snapshot().metrics['spillback_blocked_movements'] > 0


def test_exit_movements_are_never_storage_blocked():
    engine = MockTrafficEngine()
    engine.reset(seed=7)
    # J1-south leaves the network, so it always has somewhere to go.
    before = len(engine.lanes[('J1', 'south')])
    engine.step({'J1': 'NS', 'J2': 'PED', 'J3': 'PED', 'J4': 'PED'})
    assert len(engine.lanes[('J1', 'south')]) < before


# -------------------------------------------------------- gated discharge

def test_gated_pressure_prefers_the_phase_it_can_actually_discharge():
    engine = MockTrafficEngine()
    engine.reset(seed=7)
    from collections import deque
    from app.simulation.mock_engine import Vehicle

    junction = 'J3'
    # Give EW a big queue whose downstream (J4-west) is completely full, and NS
    # a smaller queue that exits the network freely.
    engine.lanes[(junction, 'west')] = deque(Vehicle(0) for _ in range(30))
    engine.lanes[(junction, 'east')] = deque()
    engine.lanes[('J4', 'west')] = deque(Vehicle(0) for _ in range(LINK_STORAGE))
    engine.lanes[(junction, 'north')] = deque(Vehicle(0) for _ in range(8))
    engine.lanes[(junction, 'south')] = deque(Vehicle(0) for _ in range(8))

    action = GatedPressureController().choose_phases(engine.snapshot())[junction]
    # Raw pressure would say EW (30 waiting); useful discharge says NS.
    assert action == 'NS'


# ---------------------------------------------------------- coordination

def test_coordination_beats_the_fixed_clock_under_normal_demand():
    queue = lambda r: r['average_network_queue']
    coordinated = pooled('coordinated-pressure-v1', 'normal', queue)
    fixed = pooled('fixed-time', 'normal', queue)

    assert coordinated < fixed
    # The effect is large, not marginal: this is the headline claim.
    assert (fixed - coordinated) / fixed > 0.20


def test_coordination_beats_local_optimisation():
    queue = lambda r: r['average_network_queue']
    coordinated = pooled('coordinated-pressure-v1', 'normal', queue)
    local = pooled('max-pressure', 'normal', queue)

    assert coordinated < local


def test_coordination_no_longer_loses_on_throughput_under_saturation():
    throughput = lambda r: float(r['throughput'])
    coordinated = pooled('coordinated-pressure-v1', 'rush', throughput)
    fixed = pooled('fixed-time', 'rush', throughput)
    local = pooled('max-pressure', 'rush', throughput)

    # The original defect was adaptive control losing throughput to a fixed
    # clock in saturation. Coordination reverses that.
    assert coordinated > fixed
    assert coordinated > local


def test_coordination_improves_the_worst_case_too():
    p95 = lambda r: r['metrics']['p95_vehicle_delay']
    assert pooled('coordinated-pressure-v1', 'rush', p95) < pooled('fixed-time', 'rush', p95)
    assert pooled('coordinated-pressure-v1', 'normal', p95) < pooled('fixed-time', 'normal', p95)


def test_junctions_hold_the_network_phase_when_nothing_is_wrong():
    engine = MockTrafficEngine()
    engine.reset(scenario='rush', seed=7)
    controller = CoordinatedPressureController()

    deviations = 0
    for _ in range(120):
        deviations += len(controller.explain(engine.snapshot())['deviating_junctions'])
        engine.step(controller.choose_phases(engine.snapshot()))

    # Coordination is the default; deviation is an exception for disruption.
    assert deviations == 0


def test_a_junction_may_break_ranks_when_its_local_case_is_overwhelming():
    engine = MockTrafficEngine()
    engine.reset(seed=7)
    from collections import deque
    from app.simulation.mock_engine import Vehicle

    def fill(jid, directions, n):
        for d in directions:
            engine.lanes[(jid, d)] = deque(Vehicle(0) for _ in range(n))

    # Three junctions clearly want NS, so the network phase is NS.
    for jid in ('J2', 'J3', 'J4'):
        fill(jid, ('north', 'south'), 20)
        fill(jid, ('east', 'west'), 0)
    # J1 has nothing at all on NS and a full EW, so holding the network phase
    # there would waste the green entirely.
    fill('J1', ('north', 'south'), 0)
    fill('J1', ('east', 'west'), 20)

    report = CoordinatedPressureController().explain(engine.snapshot())
    assert report['network_phase'] == 'NS'
    assert report['deviating_junctions'] == ['J1']


def test_no_phase_is_ever_fully_blocked_in_this_topology():
    """Every phase at every junction contains a movement that exits the network.

    This is why deviation is so rare here: a junction can always discharge
    *something* on either phase, so holding the coordinated phase is almost
    never wasteful. On a network where a phase can be completely blocked, the
    deviation threshold would earn its keep far more often.
    """
    for jid in MockTrafficEngine.JUNCTION_IDS:
        for directions in (('north', 'south'), ('east', 'west')):
            targets = [MockTrafficEngine.STRAIGHT_TRANSFERS[(jid, d)] for d in directions]
            assert None in targets, f'{jid} {directions} has no exit movement'


def test_a_zero_threshold_degenerates_to_local_greed():
    engine = MockTrafficEngine()
    engine.reset(scenario='rush', seed=7)
    greedy = SafetyShield(CoordinatedPressureController(deviation_threshold=0.0))
    coordinated = SafetyShield(CoordinatedPressureController())

    def run(controller):
        e = MockTrafficEngine()
        e.reset(scenario='rush', seed=7)
        for _ in range(120):
            e.step(controller.choose_phases(e.snapshot()))
        return e.snapshot().throughput

    assert run(coordinated) > run(greedy)
