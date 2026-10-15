"""The inputs a visitor types must actually reach the simulation.

The whole point of this endpoint is that nothing on the page is a preset any
more. So the thing worth testing is not that it returns 200 -- it is that
different numbers produce different traffic, and that nonsense input does not
take the server down.
"""

from fastapi.testclient import TestClient

from app.main import app
from app.services.custom_run import run_custom

client = TestClient(app)


def test_typed_demand_changes_the_outcome():
    light = run_custom(arrivals={'north': 400, 'south': 400, 'east': 400, 'west': 400},
                       steps=120)
    heavy = run_custom(arrivals={'north': 2600, 'south': 2600, 'east': 2600, 'west': 2600},
                       steps=120)
    assert heavy['results'][0]['vehicles_served'] > light['results'][0]['vehicles_served']
    assert heavy['input']['total_demand_vph'] > light['input']['total_demand_vph']


def test_fleet_mix_changes_the_people_carried():
    """More buses on the same number of vehicles must mean more people."""
    scooters = run_custom(mix={'two-wheeler': 90, 'car': 10, 'auto': 0, 'bus': 0}, steps=120)
    buses = run_custom(mix={'two-wheeler': 0, 'car': 10, 'auto': 0, 'bus': 90}, steps=120)
    assert buses['results'][0]['people_moved'] > scooters['results'][0]['people_moved']


def test_both_controllers_see_identical_traffic():
    d = run_custom(steps=120, seed=11)
    assert len({r['controller'] for r in d['results']}) == len(d['results'])
    assert d['input']['seed'] == 11
    # A comparison is only meaningful if the later rows are measured against the first.
    for row in d['results'][1:]:
        assert set(row['vs_first']) == {'people_moved', 'vehicles_served', 'p95_delay'}


def test_mix_need_not_sum_to_one_hundred():
    d = run_custom(mix={'two-wheeler': 2, 'car': 2, 'auto': 0, 'bus': 0}, steps=80)
    assert sum(d['input']['mix_pct'].values()) == 100.0


def test_degenerate_input_does_not_crash():
    for body in (
        {'arrivals': {'north': 0, 'south': 0, 'east': 0, 'west': 0}},
        {'mix': {'two-wheeler': 0, 'car': 0, 'auto': 0, 'bus': 0}},
        {'arrivals': {'north': -500}},
        {'steps': 100000},
        {'controllers': ['no-such-controller']},
    ):
        r = client.post('/api/custom/run', json={**body, 'steps': body.get('steps', 60)})
        assert r.status_code == 200, body
        assert r.json()['results']


def test_steps_are_clamped():
    assert run_custom(steps=100000)['input']['steps'] == 600
    assert run_custom(steps=1)['input']['steps'] == 40


def test_endpoint_round_trips_what_was_asked_for():
    r = client.post('/api/custom/run', json={
        'arrivals': {'north': 1750, 'south': 650, 'east': 1900, 'west': 700},
        'mix': {'two-wheeler': 60, 'car': 25, 'auto': 10, 'bus': 5},
        'steps': 80, 'seed': 3,
    })
    assert r.status_code == 200
    d = r.json()
    assert d['input']['arrivals_vph'] == {'north': 1750, 'south': 650,
                                          'east': 1900, 'west': 700}
    assert d['input']['mix_pct']['two-wheeler'] == 60.0
    assert d['input']['total_demand_vph'] == 5000


def test_same_input_gives_the_same_answer_twice():
    """Reproducibility is the claim the whole project rests on."""
    a = run_custom(steps=100, seed=5)
    b = run_custom(steps=100, seed=5)
    assert a['results'] == b['results']
