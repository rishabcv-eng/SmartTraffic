"""Calibrate the model against observed traffic counts.

Synthetic demand proves an algorithm works on synthetic demand. To claim
anything about a real junction, the arrival rates have to be fitted to counts
somebody actually measured -- a traffic-police survey, an ATCS export, or a
manual turning-count sheet.

Input is deliberately the simplest thing a transport department can hand over:
a CSV with one row per approach.

    junction,direction,vehicles_per_hour
    J1,north,1450
    J1,west,980

Everything else is derived. The report includes the residual between observed
and simulated flow so the fit can be judged rather than assumed.
"""

from __future__ import annotations

import csv
import io

from app.models import DIRECTIONS
from app.simulation.mock_engine import MockTrafficEngine
from app.services.impact import TICK_SECONDS

#: Mean arrivals per tick produced by the engine's base demand process
#: (uniform 0..3 vehicles), before any scaling.
BASE_ARRIVALS_PER_TICK = 1.5

#: Equivalent hourly flow of that base process.
BASE_VEHICLES_PER_HOUR = BASE_ARRIVALS_PER_TICK * 3600.0 / TICK_SECONDS

VALID_JUNCTIONS = set(MockTrafficEngine.JUNCTION_IDS)


class CalibrationError(ValueError):
    """Raised when a counts file cannot be interpreted."""


def parse_counts(csv_text: str) -> list[dict]:
    """Read a counts CSV into validated rows."""
    reader = csv.DictReader(io.StringIO(csv_text.strip()))
    if not reader.fieldnames:
        raise CalibrationError('the counts file is empty')

    headers = {h.strip().lower() for h in reader.fieldnames}
    required = {'junction', 'direction', 'vehicles_per_hour'}
    missing = required - headers
    if missing:
        raise CalibrationError(f'missing column(s): {", ".join(sorted(missing))}')

    rows: list[dict] = []
    for lineno, raw in enumerate(reader, start=2):
        clean = {(k or '').strip().lower(): (v or '').strip() for k, v in raw.items()}
        junction = clean['junction'].upper()
        direction = clean['direction'].lower()
        if junction not in VALID_JUNCTIONS:
            raise CalibrationError(f'line {lineno}: unknown junction "{junction}"')
        if direction not in DIRECTIONS:
            raise CalibrationError(f'line {lineno}: unknown direction "{direction}"')
        try:
            flow = float(clean['vehicles_per_hour'])
        except ValueError:
            raise CalibrationError(
                f'line {lineno}: vehicles_per_hour "{clean["vehicles_per_hour"]}" is not a number'
            ) from None
        if flow < 0:
            raise CalibrationError(f'line {lineno}: vehicles_per_hour cannot be negative')

        row = {
            'junction': junction,
            'direction': direction,
            'vehicles_per_hour': flow,
        }
        if 'buses_per_hour' in headers and clean.get('buses_per_hour'):
            row['buses_per_hour'] = float(clean['buses_per_hour'])
        rows.append(row)

    if not rows:
        raise CalibrationError('the counts file has headers but no data rows')
    return rows


def fit_demand(rows: list[dict]) -> dict:
    """Turn observed hourly flows into per-approach demand multipliers."""
    scales: dict[tuple[str, str], float] = {}
    for row in rows:
        key = (row['junction'], row['direction'])
        scales[key] = round(row['vehicles_per_hour'] / BASE_VEHICLES_PER_HOUR, 4)

    bus_rows = [r for r in rows if 'buses_per_hour' in r]
    bus_share = None
    if bus_rows:
        total = sum(r['vehicles_per_hour'] for r in bus_rows)
        buses = sum(r['buses_per_hour'] for r in bus_rows)
        bus_share = round(buses / max(1e-9, total), 4)

    return {'scales': scales, 'bus_share': bus_share}


def apply_calibration(engine: MockTrafficEngine, fit: dict) -> None:
    """Push a fitted demand profile onto a live engine."""
    engine.demand_scale = dict(fit['scales'])
    if fit.get('bus_share') is not None:
        engine.bus_share = fit['bus_share']


def calibrate(csv_text: str, verify_steps: int = 240, seed: int = 7) -> dict:
    """Fit demand to counts, then replay to check the fit reproduces them.

    Only the externally-fed approaches can be calibrated directly; the rest of
    the network receives its traffic from upstream junctions, so their flow is
    an output of the model rather than an input to it.
    """
    rows = parse_counts(csv_text)
    fit = fit_demand(rows)

    engine = MockTrafficEngine()
    engine.reset(seed=seed)
    apply_calibration(engine, fit)

    external = {
        (jid, d)
        for jid, dirs in MockTrafficEngine.EXTERNAL_APPROACHES.items()
        for d in dirs
    }
    baseline_lengths = {key: len(engine.lanes[key]) for key in engine.lanes}

    # Replay and read the offered-demand counter directly. Measuring queue
    # growth instead would undercount once an approach reaches its storage
    # limit, which is exactly the regime a peak-hour count is taken in.
    for _ in range(verify_steps):
        engine.step({jid: 'PED' for jid in MockTrafficEngine.JUNCTION_IDS})
    observed_arrivals = dict(engine.arrivals_seen)

    hours = verify_steps * TICK_SECONDS / 3600.0
    report = []
    for row in rows:
        key = (row['junction'], row['direction'])
        if key not in external:
            report.append({
                'junction': row['junction'],
                'direction': row['direction'],
                'observed_vph': row['vehicles_per_hour'],
                'simulated_vph': None,
                'calibratable': False,
                'note': 'internal approach fed by upstream junctions; not directly settable',
            })
            continue
        simulated = observed_arrivals[key] / max(1e-9, hours)
        residual = simulated - row['vehicles_per_hour']
        report.append({
            'junction': row['junction'],
            'direction': row['direction'],
            'observed_vph': row['vehicles_per_hour'],
            'simulated_vph': round(simulated, 1),
            'residual_vph': round(residual, 1),
            'error_pct': round(100.0 * residual / max(1e-9, row['vehicles_per_hour']), 2),
            'scale': fit['scales'][key],
            'calibratable': True,
        })

    fitted = [r for r in report if r['calibratable']]
    mean_abs_error = (
        round(sum(abs(r['error_pct']) for r in fitted) / len(fitted), 2) if fitted else None
    )

    return {
        'rows_read': len(rows),
        'approaches_fitted': len(fitted),
        'bus_share': fit['bus_share'],
        'base_vehicles_per_hour': round(BASE_VEHICLES_PER_HOUR, 1),
        'scales': {f'{j}-{d}': s for (j, d), s in fit['scales'].items()},
        'verification': report,
        'mean_absolute_error_pct': mean_abs_error,
        'baseline_queue_lengths': {f'{j}-{d}': v for (j, d), v in baseline_lengths.items()},
        'note': (
            'Demand is fitted per external approach. Internal approaches are an '
            'emergent result of upstream signal timing and are reported, not set.'
        ),
    }
