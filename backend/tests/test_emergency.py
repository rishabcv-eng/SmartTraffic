from app.services.emergency import plan_green_corridor, run_preemption_comparison


def test_corridor_schedule_leads_the_vehicle_at_every_junction():
    plan = plan_green_corridor(['J1', 'J2', 'J4'], segment_travel_seconds=[30.0, 40.0])
    schedule = plan['schedule']

    assert [s['junction_id'] for s in schedule] == ['J1', 'J2', 'J4']
    assert [s['eta_seconds'] for s in schedule] == [0.0, 30.0, 70.0]
    assert plan['total_eta_seconds'] == 70.0
    assert all(s['green_lead_seconds'] > 0 for s in schedule)


def test_priority_profiles_differ_by_vehicle_type():
    ambulance = plan_green_corridor(['J1', 'J2'], vehicle_type='ambulance')
    vip = plan_green_corridor(['J1', 'J2'], vehicle_type='vip')

    assert ambulance['priority'] > vip['priority']
    assert ambulance['max_delay_seconds'] < vip['max_delay_seconds']


def test_preemption_gets_the_ambulance_through_faster():
    result = run_preemption_comparison(steps=140, seed=7, scenario='rush')

    without = result['without_preemption']['emergency']
    with_it = result['with_preemption']['emergency']

    assert without['travel_ticks'] is not None
    assert with_it['travel_ticks'] is not None
    assert with_it['travel_ticks'] < without['travel_ticks']
    assert result['saved_seconds'] > 0
    assert result['improvement_pct'] > 0


def test_preemption_removes_red_light_waiting():
    result = run_preemption_comparison(steps=140, seed=7, scenario='rush')

    assert result['with_preemption']['emergency']['delay_ticks'] == 0
    assert result['without_preemption']['emergency']['delay_ticks'] > 0
    assert result['red_light_waits_avoided'] > 0


def test_the_cost_of_priority_is_measured_against_the_same_controller():
    result = run_preemption_comparison(steps=140, seed=7, scenario='rush')
    cost = result['cost_of_priority']

    # Both sides of this comparison run the same controller on the same seed,
    # so the difference is the ambulance and nothing else.
    assert cost['controller'] == result['with_preemption']['controller']
    assert 'network_without_ambulance' in cost
    assert 'network_with_ambulance' in cost
    assert isinstance(cost['extra_mean_vehicle_delay'], float)


def test_comparison_is_reproducible():
    a = run_preemption_comparison(steps=100, seed=13)
    b = run_preemption_comparison(steps=100, seed=13)
    assert a == b
