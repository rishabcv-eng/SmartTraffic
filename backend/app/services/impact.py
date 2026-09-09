"""Convert traffic-engineering metrics into the numbers a city actually buys.

A controller that reports "12% lower average queue" is hard for a transport
department to act on. The same result expressed as litres of fuel, tonnes of
CO2 and rupees of lost productive time is directly comparable against the cost
of installing the system.

Every constant here is an explicit, overridable assumption. They are published
in ``docs/IMPACT.md`` so a reviewer can challenge the arithmetic rather than
having to trust it.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

#: One simulation tick of wall-clock time. The engine discharges up to 5
#: vehicles per approach per tick, which at a saturation flow of ~1800 veh/h/lane
#: over two lanes corresponds to a 5-second tick.
TICK_SECONDS = 5.0


@dataclass
class ImpactAssumptions:
    """Editable inputs to the impact model. Defaults are Indian-city figures."""

    tick_seconds: float = TICK_SECONDS

    # Idle fuel consumption, litres per hour of stationary running.
    car_idle_litres_per_hour: float = 0.70
    bus_idle_litres_per_hour: float = 2.50

    # Combustion factors, kg CO2 per litre of fuel burned.
    petrol_kg_co2_per_litre: float = 2.31
    diesel_kg_co2_per_litre: float = 2.68

    # Retail fuel price, rupees per litre.
    petrol_price_inr: float = 105.0
    diesel_price_inr: float = 95.0

    # Value of travel time, rupees per person-hour of delay.
    value_of_time_inr_per_person_hour: float = 120.0

    # Annualisation: how much of a year this measured period represents.
    peak_hours_per_day: float = 14.0
    operating_days_per_year: float = 330.0

    def to_dict(self) -> dict:
        return asdict(self)


def _hours(wait_ticks: float, assumptions: ImpactAssumptions) -> float:
    return wait_ticks * assumptions.tick_seconds / 3600.0


def estimate_impact(
    metrics: dict,
    steps: int,
    assumptions: ImpactAssumptions | None = None,
) -> dict:
    """Translate one run's delay totals into fuel, emissions and rupees.

    ``metrics`` is the dict produced by ``MockTrafficEngine.wait_metrics``.
    """
    a = assumptions or ImpactAssumptions()

    total_vehicle_ticks = float(metrics.get('total_vehicle_wait_ticks', 0))
    bus_ticks = float(metrics.get('total_bus_wait_ticks', 0))
    car_ticks = max(0.0, total_vehicle_ticks - bus_ticks)
    person_ticks = float(metrics.get('total_person_wait_ticks', 0))

    car_idle_hours = _hours(car_ticks, a)
    bus_idle_hours = _hours(bus_ticks, a)

    car_litres = car_idle_hours * a.car_idle_litres_per_hour
    bus_litres = bus_idle_hours * a.bus_idle_litres_per_hour
    litres = car_litres + bus_litres

    co2_kg = (
        car_litres * a.petrol_kg_co2_per_litre
        + bus_litres * a.diesel_kg_co2_per_litre
    )
    fuel_cost = car_litres * a.petrol_price_inr + bus_litres * a.diesel_price_inr

    person_hours = _hours(person_ticks, a)
    time_cost = person_hours * a.value_of_time_inr_per_person_hour

    measured_hours = max(1e-9, steps * a.tick_seconds / 3600.0)
    annual_factor = (a.peak_hours_per_day / measured_hours) * a.operating_days_per_year
    daily_factor = a.peak_hours_per_day / measured_hours

    return {
        'measured_hours': round(measured_hours, 3),
        'idle_fuel_litres': round(litres, 2),
        'co2_kg': round(co2_kg, 2),
        'fuel_cost_inr': round(fuel_cost, 2),
        'person_hours_lost': round(person_hours, 2),
        'time_cost_inr': round(time_cost, 2),
        'total_cost_inr': round(fuel_cost + time_cost, 2),
        'per_day': {
            'idle_fuel_litres': round(litres * daily_factor, 1),
            'co2_kg': round(co2_kg * daily_factor, 1),
            'total_cost_inr': round((fuel_cost + time_cost) * daily_factor, 0),
        },
        'per_year': {
            'idle_fuel_litres': round(litres * annual_factor, 0),
            'co2_tonnes': round(co2_kg * annual_factor / 1000.0, 1),
            'total_cost_inr': round((fuel_cost + time_cost) * annual_factor, 0),
        },
        'assumptions': a.to_dict(),
    }


def compare_impact(
    baseline: dict,
    candidate: dict,
    steps: int,
    assumptions: ImpactAssumptions | None = None,
    junctions: int = 4,
) -> dict:
    """Savings of ``candidate`` against ``baseline``, in city-budget terms."""
    a = assumptions or ImpactAssumptions()
    base = estimate_impact(baseline, steps, a)
    cand = estimate_impact(candidate, steps, a)

    def saved(path: str, key: str) -> float:
        return round(base[path][key] - cand[path][key], 2) if path else 0.0

    fuel_saved_year = base['per_year']['idle_fuel_litres'] - cand['per_year']['idle_fuel_litres']
    co2_saved_year = base['per_year']['co2_tonnes'] - cand['per_year']['co2_tonnes']
    money_saved_year = base['per_year']['total_cost_inr'] - cand['per_year']['total_cost_inr']

    def pct(before: float, after: float) -> float:
        return round(100.0 * (before - after) / max(1e-9, before), 2)

    return {
        'baseline': base,
        'candidate': cand,
        'saved_per_day': {
            'idle_fuel_litres': saved('per_day', 'idle_fuel_litres'),
            'co2_kg': saved('per_day', 'co2_kg'),
            'total_cost_inr': saved('per_day', 'total_cost_inr'),
        },
        'saved_per_year': {
            'idle_fuel_litres': round(fuel_saved_year, 0),
            'co2_tonnes': round(co2_saved_year, 1),
            'total_cost_inr': round(money_saved_year, 0),
            'total_cost_inr_crore': round(money_saved_year / 1e7, 3),
        },
        'reduction_pct': {
            'idle_fuel': pct(base['idle_fuel_litres'], cand['idle_fuel_litres']),
            'co2': pct(base['co2_kg'], cand['co2_kg']),
            'person_hours': pct(base['person_hours_lost'], cand['person_hours_lost']),
        },
        'scope': {
            'junctions_measured': junctions,
            'note': (
                'Figures cover the modelled corridor only. Scaling to a whole city '
                'requires per-junction demand calibration.'
            ),
        },
    }
