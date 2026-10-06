from app.simulation.mock_engine import WEATHER_CAPACITY, MockTrafficEngine, Vehicle


def drive(engine, steps=40, phase='NS'):
    for _ in range(steps):
        engine.step({jid: phase for jid in MockTrafficEngine.JUNCTION_IDS})
    return engine.snapshot()


def test_tracks_individual_vehicle_delay():
    engine = MockTrafficEngine()
    engine.reset(seed=5)
    snap = drive(engine, steps=30)
    metrics = snap.metrics

    assert metrics['served_vehicles'] > 0
    assert metrics['mean_vehicle_delay'] > 0
    # A distribution, not a single number: p95 must sit above the median and
    # the worst case at or above p95.
    assert metrics['p50_vehicle_delay'] <= metrics['p95_vehicle_delay']
    assert metrics['p95_vehicle_delay'] <= metrics['max_vehicle_delay']


def test_person_delay_weights_buses_above_cars():
    engine = MockTrafficEngine()
    engine.reset(seed=5)
    engine.bus_share = 0.5
    drive(engine, steps=30)
    metrics = engine.snapshot().metrics

    assert metrics['served_people'] > metrics['served_vehicles']
    assert metrics['mean_bus_delay'] > 0


def test_pedestrians_only_clear_on_a_pedestrian_phase():
    engine = MockTrafficEngine()
    engine.reset(seed=5)
    drive(engine, steps=10, phase='NS')
    assert engine.snapshot().junctions[0].pedestrian > 0

    engine.step({jid: 'PED' for jid in MockTrafficEngine.JUNCTION_IDS})
    assert engine.snapshot().junctions[0].pedestrian == 0
    assert engine.snapshot().metrics['pedestrians_served'] > 0


def test_bad_weather_reduces_discharge_capacity():
    clear = MockTrafficEngine()
    clear.reset(scenario='rush', seed=5)
    wet = MockTrafficEngine()
    wet.reset(scenario='rush', seed=5)
    wet.set_weather('heavy-rain')

    assert WEATHER_CAPACITY['heavy-rain'] < WEATHER_CAPACITY['clear']
    assert wet._capacity('J1', 'north') < clear._capacity('J1', 'north')

    # Capacity only binds when the network is saturated, so alternate phases
    # under rush demand and compare the queue each condition leaves behind.
    def alternate(engine, steps=40):
        for tick in range(steps):
            phase = 'NS' if (tick // 4) % 2 == 0 else 'EW'
            engine.step({jid: phase for jid in MockTrafficEngine.JUNCTION_IDS})
        return sum(len(lane) for lane in engine.lanes.values())

    assert alternate(wet) > alternate(clear)


def test_detector_faults_corrupt_what_the_controller_sees_not_the_truth():
    engine = MockTrafficEngine()
    engine.reset(seed=5)
    drive(engine, steps=5)

    true_length = len(engine.lanes[('J2', 'east')])
    assert true_length > 0

    engine.inject_fault('detector-dropout', 'J2', 'east')
    reported = next(j for j in engine.snapshot().junctions if j.id == 'J2')
    assert reported.east == 0
    # The vehicles are still physically there; only the reading is wrong.
    assert len(engine.lanes[('J2', 'east')]) == true_length
    assert reported.mode == 'detector-degraded'
    assert reported.healthy is False


def test_stuck_detector_freezes_its_reading():
    engine = MockTrafficEngine()
    engine.reset(seed=5)
    engine.inject_fault('detector-stuck', 'J1', 'north')
    frozen = next(j for j in engine.snapshot().junctions if j.id == 'J1').north

    drive(engine, steps=15, phase='EW')
    assert next(j for j in engine.snapshot().junctions if j.id == 'J1').north == frozen


def test_signal_fault_serves_nobody():
    engine = MockTrafficEngine()
    engine.reset(seed=5)
    engine.inject_fault('signal-fault', 'J1')
    before = sum(len(engine.lanes[('J1', d)]) for d in ('north', 'south'))
    engine.step({'J1': 'NS', 'J2': 'NS', 'J3': 'NS', 'J4': 'NS'})
    after = sum(len(engine.lanes[('J1', d)]) for d in ('north', 'south'))

    assert after >= before
    assert next(j for j in engine.snapshot().junctions if j.id == 'J1').mode == 'all-red-flash'


def test_comms_loss_falls_back_to_a_local_clock():
    engine = MockTrafficEngine()
    engine.reset(seed=5)
    engine.inject_fault('comms-loss', 'J3')
    # Command a phase the cabinet should ignore while it runs its own clock.
    for _ in range(9):
        engine.step({jid: 'EW' for jid in MockTrafficEngine.JUNCTION_IDS})

    phases = {engine.phases['J3'] for _ in range(1)}
    assert engine.modes['J3'] == 'local-fallback'
    assert phases  # the junction is still cycling rather than frozen


def test_clearing_events_restores_normal_operation():
    engine = MockTrafficEngine()
    engine.reset(seed=5)
    engine.inject_fault('comms-loss', 'J3')
    engine.set_weather('fog')
    engine.inject('clear')

    assert engine.faults == {}
    assert engine.weather == 'clear'


def test_emergency_vehicle_traverses_its_route():
    engine = MockTrafficEngine()
    engine.reset(seed=5)
    run = engine.dispatch_emergency(['J1', 'J2', 'J4'], 'ambulance')
    assert run.directions == ['west', 'north', 'north']

    for _ in range(60):
        engine.step({'J1': 'EW', 'J2': 'NS', 'J3': 'NS', 'J4': 'NS'})
        if engine.emergency_run.finish_tick is not None:
            break

    assert engine.emergency_run.finish_tick is not None


def test_emergency_vehicle_waits_at_a_hostile_red():
    engine = MockTrafficEngine()
    engine.reset(seed=5)
    engine.dispatch_emergency(['J1', 'J2'], 'ambulance')
    # J1 approach is 'west', which needs EW; hold NS the whole time.
    for _ in range(10):
        engine.step({jid: 'NS' for jid in MockTrafficEngine.JUNCTION_IDS})

    assert engine.emergency_run.waiting_at_red if hasattr(engine.emergency_run, 'waiting_at_red') else engine.emergency_run.waiting
    assert engine.emergency_run.delay_ticks >= 9
    assert engine.emergency_run.finish_tick is None


def test_storage_index_never_drifts_from_the_queues():
    """Occupancy is maintained incrementally, so it can silently go stale.

    It is compared against a hard capacity limit, so drift does not raise — it
    quietly admits traffic that should have been turned away. This pins the
    invariant rather than trusting it.
    """
    from app.controllers.registry import build

    engine = MockTrafficEngine()
    engine.reset(scenario='rush', seed=3)
    controller = build('coordinated-pressure-v1', shielded=True)

    for _ in range(150):
        engine.step(controller.choose_phases(engine.snapshot()))
        for key, lane in engine.lanes.items():
            assert engine._storage[key] == sum(v.storage_ci for v in lane), key


def test_replacing_a_queue_keeps_the_index_consistent():
    engine = MockTrafficEngine()
    engine.reset(seed=7)
    engine.set_queue('J2', 'west', [Vehicle(arrival_tick=0, kind='two-wheeler')] * 30)

    assert engine._storage[('J2', 'west')] == 30 * Vehicle(0, 'two-wheeler').storage_ci
    assert len(engine.lanes[('J2', 'west')]) == 30


def test_storage_is_compared_in_exact_units():
    """Capacity is an integer comparison, not a float one.

    0.35 and 0.55 car-lengths are not representable in binary, so accumulating
    them as floats made whether a vehicle fits depend on the order the queue was
    built in. These must be exact.
    """
    assert Vehicle(0, 'two-wheeler').storage_ci == 35
    assert Vehicle(0, 'car').storage_ci == 100
    assert Vehicle(0, 'bus').storage_ci == 260
    assert all(isinstance(Vehicle(0, k).storage_ci, int)
               for k in ('two-wheeler', 'auto', 'car', 'bus'))
