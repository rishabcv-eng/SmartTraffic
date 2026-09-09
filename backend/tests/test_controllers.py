from app.controllers.predictive_pressure import PredictivePressureController
from app.controllers.registry import CONTROLLERS, build, describe
from app.simulation.mock_engine import MockTrafficEngine


def test_controllers_emit_all_junction_actions():
    engine = MockTrafficEngine()
    snap = engine.reset(seed=3)
    for name in CONTROLLERS:
        actions = build(name).choose_phases(snap)
        assert set(actions) == {'J1', 'J2', 'J3', 'J4'}, name
        # Only the safety shield may introduce a pedestrian phase.
        assert set(actions.values()) <= {'NS', 'EW', 'PED'}, name


def test_registry_describes_every_controller():
    detail = describe()
    assert len(detail) == len(CONTROLLERS)
    assert all(row['summary'] for row in detail)
    assert any(row['shield_required'] for row in detail)


def test_simulation_is_deterministic():
    a, b = MockTrafficEngine(), MockTrafficEngine()
    a.reset(seed=11); b.reset(seed=11)
    controller_a = PredictivePressureController(); controller_b = PredictivePressureController()
    for _ in range(20):
        sa, sb = a.snapshot(), b.snapshot()
        a.step(controller_a.choose_phases(sa)); b.step(controller_b.choose_phases(sb))
    assert a.snapshot().to_dict() == b.snapshot().to_dict()
