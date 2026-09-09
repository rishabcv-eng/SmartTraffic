"""Hardware bridge and the shielded reinforcement-learning controller."""

from app.controllers.registry import build
from app.controllers.rl_controller import RLController, bucket, encode, train_policy
from app.controllers.safety import SafetyShield
from app.services.hil import SignalHeadBridge
from app.simulation.mock_engine import MockTrafficEngine


# ------------------------------------------------------------ hardware bridge

def test_aspects_match_the_commanded_phase():
    engine = MockTrafficEngine()
    engine.reset(seed=5)
    bridge = SignalHeadBridge()

    engine.step({jid: 'NS' for jid in MockTrafficEngine.JUNCTION_IDS})
    head = bridge.render(engine.snapshot())['heads'][0]

    assert head['ns'] == 'green'
    assert head['ew'] == 'red'
    assert head['code'] == 'GRR'


def test_a_phase_change_shows_amber_on_the_losing_movement():
    engine = MockTrafficEngine()
    engine.reset(seed=5)
    bridge = SignalHeadBridge(amber_ticks=1)

    engine.step({jid: 'NS' for jid in MockTrafficEngine.JUNCTION_IDS})
    bridge.render(engine.snapshot())
    engine.step({jid: 'EW' for jid in MockTrafficEngine.JUNCTION_IDS})
    head = bridge.render(engine.snapshot())['heads'][0]

    # NS is giving up right of way, so NS shows amber and nothing shows green.
    assert head['ns'] == 'amber'
    assert head['ew'] == 'red'
    assert head['code'] == 'ARR'


def test_pedestrian_phase_lights_the_pedestrian_aspect():
    engine = MockTrafficEngine()
    engine.reset(seed=5)
    bridge = SignalHeadBridge(amber_ticks=0)

    engine.step({jid: 'PED' for jid in MockTrafficEngine.JUNCTION_IDS})
    head = bridge.render(engine.snapshot())['heads'][0]

    assert head['ped'] == 'green'
    assert head['ns'] == 'red' and head['ew'] == 'red'


def test_a_failed_head_never_shows_green():
    engine = MockTrafficEngine()
    engine.reset(seed=5)
    engine.inject_fault('signal-fault', 'J1')
    bridge = SignalHeadBridge()

    engine.step({jid: 'NS' for jid in MockTrafficEngine.JUNCTION_IDS})
    head = next(h for h in bridge.render(engine.snapshot())['heads'] if h['id'] == 'J1')

    assert head['fault'] is True
    assert head['code'] == 'RRR'
    assert 'green' not in (head['ns'], head['ew'], head['ped'])


def test_wire_format_is_parseable_by_a_microcontroller():
    engine = MockTrafficEngine()
    engine.reset(seed=5)
    bridge = SignalHeadBridge()
    engine.step({jid: 'NS' for jid in MockTrafficEngine.JUNCTION_IDS})

    payload = bridge.render(engine.snapshot())
    fields = payload['wire'].split('|')

    assert fields[0] == f'T{payload["tick"]}'
    assert len(fields) == 5
    for field in fields[1:]:
        jid, code = field.split(':')
        assert jid in MockTrafficEngine.JUNCTION_IDS
        assert len(code) == 3
        assert set(code) <= {'G', 'A', 'R'}


# ---------------------------------------------------------------------- RL

def test_state_buckets_are_monotonic():
    from app.controllers.rl_controller import BUCKET_EDGES

    assert bucket(0) == 0
    assert bucket(BUCKET_EDGES[0] - 1) == 0
    assert bucket(BUCKET_EDGES[0]) == 1
    assert bucket(10_000) == len(BUCKET_EDGES)
    # Buckets must never go backwards as pressure rises.
    values = [bucket(v) for v in range(0, 400, 7)]
    assert values == sorted(values)
    assert encode(1, 100, 'NS')[2] == 0
    assert encode(1, 100, 'EW')[2] == 1


def test_training_is_cached_and_deterministic():
    first = train_policy()
    second = train_policy()

    assert first is second, 'the policy should be trained once and reused'
    assert len(first) > 0
    assert all(len(v) == 2 for v in first.values())


def test_policy_produces_valid_actions_for_every_junction():
    engine = MockTrafficEngine()
    snapshot = engine.reset(seed=3)
    actions = RLController().choose_phases(snapshot)

    assert set(actions) == set(MockTrafficEngine.JUNCTION_IDS)
    assert set(actions.values()) <= {'NS', 'EW'}


def test_rl_runs_are_reproducible():
    def run(seed):
        engine = MockTrafficEngine()
        engine.reset(seed=seed)
        controller = RLController()
        for _ in range(25):
            engine.step(controller.choose_phases(engine.snapshot()))
        return engine.snapshot().to_dict()

    assert run(11) == run(11)


def test_the_registry_always_shields_the_learned_controller():
    controller = build('rl-network-v2')

    assert isinstance(controller, SafetyShield)
    assert controller.name == 'rl-network-v2+shield'


def test_the_policy_can_explain_itself():
    engine = MockTrafficEngine()
    snapshot = engine.reset(seed=3)
    row = RLController().explain(snapshot)

    assert {'pressure_ns', 'pressure_ew', 'state', 'q_ns', 'q_ew', 'known_state'} <= set(row)
    assert row['states_learned'] > 0


def test_the_policy_commands_one_phase_across_the_network():
    # Coordination is the entire point of the rewrite: independent per-junction
    # agents were the worst controller in the benchmark by a wide margin.
    engine = MockTrafficEngine()
    snapshot = engine.reset(seed=3)
    actions = RLController().choose_phases(snapshot)

    assert len(set(actions.values())) == 1


def test_the_reward_is_not_gameable_by_refusing_traffic():
    """A queue-length reward teaches the policy to block arrivals.

    Holding an approach at red lets it fill to storage, after which it refuses
    new vehicles: the network looks emptier while serving fewer people. The
    trained policy must not beat a plain fixed clock on that trick.
    """
    from app.services.scenario import ScenarioConfig, simulate

    seeds = (3, 7, 11)
    learned = [simulate(ScenarioConfig(controller='rl-network-v2', steps=140,
                                       seed=s, scenario='rush')) for s in seeds]
    fixed = [simulate(ScenarioConfig(controller='fixed-time', steps=140,
                                     seed=s, scenario='rush')) for s in seeds]

    learned_served = sum(r['metrics']['served_vehicles'] for r in learned)
    fixed_served = sum(r['metrics']['served_vehicles'] for r in fixed)
    assert learned_served >= fixed_served * 0.98
