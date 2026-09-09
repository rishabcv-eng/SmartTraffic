from app.controllers.base import Controller
from app.controllers.safety import SafetyShield
from app.simulation.mock_engine import MockTrafficEngine


class AlwaysSwitch(Controller):
    """Worst-case optimiser: proposes the opposite phase every single tick."""

    name = 'always-switch'

    def choose_phases(self, snapshot):
        return {j.id: ('EW' if j.phase == 'NS' else 'NS') for j in snapshot.junctions}


class AlwaysNS(Controller):
    name = 'always-ns'

    def choose_phases(self, snapshot):
        return {j.id: 'NS' for j in snapshot.junctions}


def test_minimum_green_blocks_flicker():
    engine = MockTrafficEngine()
    engine.reset(seed=5)
    shield = SafetyShield(AlwaysSwitch(), min_green=4, max_green=99)

    switches = 0
    previous = None
    for _ in range(20):
        actions = shield.choose_phases(engine.snapshot())
        if previous is not None and actions['J1'] != previous:
            switches += 1
        previous = actions['J1']
        engine.step(actions)

    # Without the shield this would switch on all 19 transitions.
    assert switches <= 20 / 4 + 1
    assert any(d['reason'] == 'min-green-hold' for d in shield.audit)


def test_maximum_green_prevents_starvation():
    engine = MockTrafficEngine()
    engine.reset(seed=5)
    shield = SafetyShield(AlwaysNS(), min_green=1, max_green=6, max_pedestrian_wait=999)

    phases = []
    for _ in range(20):
        actions = shield.choose_phases(engine.snapshot())
        phases.append(actions['J1'])
        engine.step(actions)

    assert 'EW' in phases, 'the cross road must be served despite the optimiser'
    assert any(d['reason'] == 'max-green-starvation-guard' for d in shield.audit)


def test_pedestrian_wait_is_capped():
    engine = MockTrafficEngine()
    engine.reset(seed=5)
    shield = SafetyShield(AlwaysNS(), max_pedestrian_wait=8, max_green=999)

    for _ in range(30):
        engine.step(shield.choose_phases(engine.snapshot()))

    metrics = engine.snapshot().metrics
    assert metrics['pedestrians_served'] > 0
    assert any(d['reason'] == 'pedestrian-max-wait' for d in shield.audit)
    # The guarantee is on the wait, so nobody should exceed the cap by much.
    assert metrics['max_pedestrian_delay'] <= 8 + 2


def test_emergency_preemption_holds_the_corridor():
    engine = MockTrafficEngine()
    engine.reset(seed=5)
    shield = SafetyShield(AlwaysNS())
    engine.dispatch_emergency(['J1', 'J2'], 'ambulance')

    for _ in range(25):
        actions = shield.choose_phases(engine.snapshot())
        engine.step(actions)
        if engine.emergency_run.finish_tick is not None:
            break

    assert engine.emergency_run.finish_tick is not None
    assert engine.emergency_run.delay_ticks == 0
    assert any(d['reason'] == 'emergency-preemption' for d in shield.audit)


def test_faults_route_to_the_documented_fallback():
    engine = MockTrafficEngine()
    engine.reset(seed=5)
    shield = SafetyShield(AlwaysNS())

    engine.inject_fault('comms-loss', 'J2')
    engine.inject_fault('detector-dropout', 'J3', 'west')
    engine.inject_fault('signal-fault', 'J4')
    for _ in range(4):
        engine.step(shield.choose_phases(engine.snapshot()))

    reasons = {d['junction']: d['reason'] for d in shield.decisions}
    assert reasons['J2'] == 'comms-loss'
    assert reasons['J3'] == 'detector-fault-fallback'
    assert reasons['J4'] == 'signal-fault'
    assert reasons['J1'] in ('accepted', 'min-green-hold', 'max-green-starvation-guard')


def test_every_decision_is_explained_and_auditable():
    engine = MockTrafficEngine()
    engine.reset(seed=5)
    shield = SafetyShield(AlwaysSwitch())

    for _ in range(10):
        engine.step(shield.choose_phases(engine.snapshot()))

    summary = shield.override_summary()
    assert summary['decisions_logged'] == 40  # 4 junctions x 10 ticks
    assert 0 <= summary['override_rate_pct'] <= 100

    for row in shield.recent_decisions(limit=5):
        assert row['explanation']
        assert row['reason'] in summary['reasons']
        assert row['overridden'] == (row['applied'] != row['proposed'])
        # The audit has to carry the evidence, not just the verdict.
        assert 'pressure_ns' in row and 'person_pressure_ns' in row

    assert shield.recent_decisions(junction='J1')[0]['junction'] == 'J1'
