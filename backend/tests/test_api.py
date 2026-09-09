import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        c.post('/api/reset', json={'controller': 'predictive-pressure-v2', 'seed': 7})
        yield c


def test_health_reports_the_shielded_controller(client):
    body = client.get('/health').json()

    assert body['status'] == 'ok'
    assert body['shielded'] is True
    assert body['controller'].endswith('+shield')
    assert 'transit-priority-v1' in body['controllers']


def test_state_exposes_the_new_metrics(client):
    client.post('/api/step')
    body = client.get('/api/state').json()

    assert 'metrics' in body and 'p95_vehicle_delay' in body['metrics']
    assert 'pedestrians_waiting' in body
    assert body['degraded'] is False
    assert body['weather'] == 'clear'


def test_faults_degrade_the_junction_and_can_be_cleared(client):
    body = client.post('/api/fault', json={'kind': 'comms-loss', 'junction': 'J3'}).json()
    assert body['degraded'] is True
    assert any(f['junction'] == 'J3' for f in body['faults'])

    cleared = client.post('/api/faults/clear').json()
    assert cleared['degraded'] is False
    assert cleared['faults'] == []


def test_weather_is_applied(client):
    body = client.post('/api/weather', json={'condition': 'heavy-rain'}).json()
    assert body['weather'] == 'heavy-rain'


def test_audit_explains_each_decision(client):
    for _ in range(5):
        client.post('/api/step')
    body = client.get('/api/safety/audit?limit=8').json()

    assert body['shielded'] is True
    assert body['constraints']['max_pedestrian_wait'] > 0
    assert body['decisions']
    for row in body['decisions']:
        assert row['explanation']


def test_audit_can_be_filtered_to_one_junction(client):
    for _ in range(5):
        client.post('/api/step')
    body = client.get('/api/safety/audit?junction=J2').json()

    assert {row['junction'] for row in body['decisions']} == {'J2'}


def test_greenwave_endpoint_returns_a_diagram(client):
    body = client.get('/api/greenwave?corridor=J1,J2,J4&cycle=16&green=8').json()

    assert len(body['junctions']) == 3
    assert body['band']['efficiency_pct'] >= body['band']['uncoordinated_efficiency_pct']


def test_greenwave_rejects_a_single_junction(client):
    assert client.get('/api/greenwave?corridor=J1').status_code == 400


def test_hil_returns_json_and_wire_formats(client):
    client.post('/api/step')

    payload = client.get('/api/hil/state').json()
    assert len(payload['heads']) == 4

    wire = client.get('/api/hil/state?format=wire')
    assert wire.headers['content-type'].startswith('text/plain')
    assert wire.text.startswith('T')


def test_calibration_reports_errors_clearly(client):
    ok = client.post('/api/calibrate', json={
        'csv_text': 'junction,direction,vehicles_per_hour\nJ1,north,1450\n',
        'verify_steps': 120,
    })
    assert ok.status_code == 200
    assert ok.json()['approaches_fitted'] == 1

    bad = client.post('/api/calibrate', json={'csv_text': 'nonsense\n1\n'})
    assert bad.status_code == 400
    assert 'missing column' in bad.json()['detail']


def test_whatif_returns_intervals(client):
    body = client.post('/api/whatif', json={
        'controllers': ['fixed-time', 'max-pressure'],
        'seeds': [3, 7], 'steps': 30,
    }).json()

    candidate = body['results'][1]
    assert candidate['metrics']['average_network_queue']['n'] == 2
    assert 'vs_baseline' in candidate


def test_impact_comparison_returns_city_scale_numbers(client):
    body = client.post('/api/impact/compare', json={
        'baseline': 'fixed-time', 'candidate': 'predictive-pressure-v2',
        'steps': 60, 'seed': 7, 'scenario': 'rush',
    }).json()

    assert 'saved_per_year' in body
    assert 'co2_tonnes' in body['saved_per_year']
    assert body['baseline']['assumptions']['tick_seconds'] > 0


def test_emergency_dispatch_and_comparison(client):
    dispatched = client.post('/api/emergency/dispatch', json={'route': ['J1', 'J2', 'J4']}).json()
    assert dispatched['emergency']['active'] is True

    body = client.get('/api/emergency/comparison?steps=100&seed=7').json()
    assert body['saved_seconds'] > 0


def test_vision_apply_requires_a_prior_analysis(client):
    body = client.post('/api/vision/apply', json={'junction': 'J1', 'corrections': {}})
    assert body.status_code == 409


def test_benchmark_suite_includes_every_controller(client):
    body = client.get('/api/benchmark/suite?steps=30').json()

    assert len(body['summary']) == 8
    assert body['best_controller']
    assert 'impact_vs_fixed_time' in body
