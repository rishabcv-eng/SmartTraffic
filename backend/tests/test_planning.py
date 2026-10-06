"""Green wave, calibration and the what-if console."""

import pytest

from app.services.calibration import CalibrationError, calibrate, fit_demand, parse_counts
from app.services.greenwave import plan_green_wave
from app.services.whatif import run_whatif

COUNTS = (
    'junction,direction,vehicles_per_hour,buses_per_hour\n'
    'J1,north,1450,90\n'
    'J1,west,980,40\n'
    'J2,east,1200,60\n'
)


# ----------------------------------------------------------------- green wave

def test_offsets_follow_platoon_travel_time():
    plan = plan_green_wave(['J1', 'J2', 'J4'], cycle=16, green=8, travel_ticks=[4, 4])
    offsets = [j['offset_ticks'] for j in plan['junctions']]

    assert offsets == [0.0, 4.0, 8.0]
    assert plan['junctions'][1]['position_m'] > plan['junctions'][0]['position_m']
    assert plan['junctions'][0]['offset_seconds'] == 0.0


def test_coordination_beats_no_coordination():
    plan = plan_green_wave(['J1', 'J2', 'J4'], cycle=16, green=8, travel_ticks=[4, 4])
    band = plan['band']

    assert band['coordinated_ticks'] > band['uncoordinated_ticks']
    assert band['efficiency_pct'] > band['uncoordinated_efficiency_pct']
    assert band['stops_avoided_per_platoon'] == 2


def test_diagram_has_a_trajectory_through_every_junction():
    plan = plan_green_wave(['J1', 'J2'], cycle=16, green=8, cycles_to_plot=3)

    assert len(plan['trajectories']) == 3
    for line in plan['trajectories']:
        assert len(line) == 2
        assert line[1]['t'] > line[0]['t']
    for junction in plan['junctions']:
        assert len(junction['green_windows']) == 3


def test_green_wave_rejects_bad_input():
    with pytest.raises(ValueError):
        plan_green_wave(['J1'])
    with pytest.raises(ValueError):
        plan_green_wave(['J1', 'J2'], travel_ticks=[4, 4])


# ---------------------------------------------------------------- calibration

def test_counts_parse_into_validated_rows():
    rows = parse_counts(COUNTS)
    assert len(rows) == 3
    assert rows[0] == {
        'junction': 'J1', 'direction': 'north',
        'vehicles_per_hour': 1450.0, 'buses_per_hour': 90.0,
    }


@pytest.mark.parametrize('bad,message', [
    ('junction,direction\nJ1,north\n', 'vehicles_per_hour'),
    ('junction,direction,vehicles_per_hour\nJ9,north,100\n', 'unknown junction'),
    ('junction,direction,vehicles_per_hour\nJ1,up,100\n', 'unknown direction'),
    ('junction,direction,vehicles_per_hour\nJ1,north,lots\n', 'not a number'),
    ('junction,direction,vehicles_per_hour\nJ1,north,-5\n', 'negative'),
    ('junction,direction,vehicles_per_hour\n', 'no data rows'),
])
def test_bad_counts_are_rejected_with_a_useful_message(bad, message):
    with pytest.raises(CalibrationError) as exc:
        parse_counts(bad)
    assert message in str(exc.value)


def test_demand_scale_is_proportional_to_observed_flow():
    fit = fit_demand(parse_counts(COUNTS))
    heavy = fit['scales'][('J1', 'north')]
    light = fit['scales'][('J1', 'west')]

    assert heavy > light > 0
    assert fit['bus_share'] == pytest.approx(190 / 3630, abs=1e-3)


def test_calibration_reproduces_the_counts_it_was_given():
    report = calibrate(COUNTS, verify_steps=400)
    fitted = [r for r in report['verification'] if r['calibratable']]

    assert fitted, 'external approaches should be calibratable'
    assert report['mean_absolute_error_pct'] < 20
    for row in fitted:
        assert row['simulated_vph'] > 0


def test_internal_approaches_are_reported_not_fitted():
    # J2-west receives its traffic from J1-west, so its flow is an output of
    # the model rather than something demand calibration can set.
    report = calibrate('junction,direction,vehicles_per_hour\nJ2,west,900\n', verify_steps=100)
    row = report['verification'][0]

    assert row['calibratable'] is False
    assert 'upstream' in row['note']


# ------------------------------------------------------------------- what-if

def test_whatif_returns_paired_intervals_against_the_baseline():
    result = run_whatif(
        controllers=['fixed-time', 'predictive-pressure-v2'],
        seeds=[3, 7, 11], steps=40,
    )
    candidate = next(r for r in result['results'] if r['controller'] == 'predictive-pressure-v2')
    delta = candidate['vs_baseline']['average_network_queue']

    assert delta['n'] == 3
    assert delta['ci_low'] <= delta['mean'] <= delta['ci_high']
    assert isinstance(delta['significant'], bool)
    assert result['results'][0]['controller'] == 'fixed-time'
    assert 'vs_baseline' not in result['results'][0]


def test_whatif_records_the_question_it_answered():
    result = run_whatif(
        controllers=['fixed-time', 'max-pressure'], seeds=[3, 7], steps=30,
        demand_multiplier=1.4, weather='rain',
        lane_closure={'kind': 'signal-fault', 'junction': 'J3'},
    )

    assert result['question']['demand_multiplier'] == 1.4
    assert result['question']['weather'] == 'rain'
    assert result['question']['lane_closure']['junction'] == 'J3'


def test_higher_demand_produces_longer_queues():
    light = run_whatif(controllers=['fixed-time'], seeds=[3, 7], steps=40, demand_multiplier=1.0)
    heavy = run_whatif(controllers=['fixed-time'], seeds=[3, 7], steps=40, demand_multiplier=2.0)

    assert (
        heavy['results'][0]['metrics']['average_network_queue']['mean']
        > light['results'][0]['metrics']['average_network_queue']['mean']
    )
