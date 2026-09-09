import pytest

from app.services.impact import ImpactAssumptions, compare_impact, estimate_impact


def metrics(vehicle_ticks=1000, bus_ticks=100, person_ticks=3000):
    return {
        'total_vehicle_wait_ticks': vehicle_ticks,
        'total_bus_wait_ticks': bus_ticks,
        'total_person_wait_ticks': person_ticks,
    }


def test_impact_scales_with_delay():
    low = estimate_impact(metrics(500, 50, 1500), steps=180)
    high = estimate_impact(metrics(1000, 100, 3000), steps=180)

    assert high['idle_fuel_litres'] > low['idle_fuel_litres'] > 0
    assert high['co2_kg'] > low['co2_kg']
    assert high['person_hours_lost'] > low['person_hours_lost']
    assert high['total_cost_inr'] == high['fuel_cost_inr'] + high['time_cost_inr']


def test_zero_delay_costs_nothing():
    result = estimate_impact(metrics(0, 0, 0), steps=180)
    assert result['idle_fuel_litres'] == 0
    assert result['total_cost_inr'] == 0


def test_buses_burn_diesel_at_the_bus_rate():
    car_only = estimate_impact(metrics(1000, 0, 1500), steps=180)
    with_buses = estimate_impact(metrics(1000, 500, 1500), steps=180)

    # Same total vehicle delay, but half of it now sits in idling buses, which
    # burn considerably more fuel per hour than a car.
    assert with_buses['idle_fuel_litres'] > car_only['idle_fuel_litres']


def test_assumptions_are_overridable():
    default = estimate_impact(metrics(), steps=180)
    pricey = estimate_impact(
        metrics(), steps=180,
        assumptions=ImpactAssumptions(value_of_time_inr_per_person_hour=1200.0),
    )

    assert pricey['time_cost_inr'] == default['time_cost_inr'] * 10
    assert pricey['assumptions']['value_of_time_inr_per_person_hour'] == 1200.0


def test_comparison_reports_savings_for_a_better_controller():
    result = compare_impact(
        baseline=metrics(2000, 200, 6000),
        candidate=metrics(1000, 100, 3000),
        steps=180,
    )

    assert result['saved_per_year']['co2_tonnes'] > 0
    assert result['saved_per_year']['total_cost_inr'] > 0
    # Rounding in the reported figures means this is 50% to within a rounding
    # step, not to the last decimal place.
    assert result['reduction_pct']['co2'] == pytest.approx(50.0, abs=0.1)
    assert result['reduction_pct']['person_hours'] == pytest.approx(50.0, abs=0.1)


def test_a_worse_candidate_reports_negative_savings():
    result = compare_impact(
        baseline=metrics(1000, 100, 3000),
        candidate=metrics(2000, 200, 6000),
        steps=180,
    )
    assert result['saved_per_year']['total_cost_inr'] < 0
    assert result['reduction_pct']['co2'] < 0
