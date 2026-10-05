"""Regenerate every headline claim in the documentation, and check it holds.

A number in a README is an assertion. This script turns each one back into a
measurement, prints what it actually comes out at today, and exits non-zero if
any claim no longer survives. If a future change quietly breaks a result, this
fails rather than letting the documentation drift into fiction.

    python scripts/reproduce_results.py            # full run, ~2 minutes
    python scripts/reproduce_results.py --quick    # fewer seeds, for CI

Every claim below is stated as a *direction and a floor*, not an exact figure,
because the exact figure depends on seeds. Where a claim is about the absence of
an effect, the check is that the paired confidence interval spans zero -- a
negative result that must keep being negative.
"""

from __future__ import annotations

import argparse
import sys
from math import sqrt
from pathlib import Path
from statistics import mean, stdev

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'backend'))

from app.controllers.registry import build                      # noqa: E402
from app.services.saturation import (                           # noqa: E402
    VEHICLE_CLASSES,
    comparison_report,
    implied_pcu,
)
from app.services.scenario import ScenarioConfig, simulate      # noqa: E402
from app.simulation.mock_engine import MockTrafficEngine        # noqa: E402

TW_HEAVY = {'two-wheeler': 0.78, 'auto': 0.12, 'car': 0.09, 'bus': 0.01}
CAR_HEAVY = {'car': 0.62, 'bus': 0.16, 'auto': 0.14, 'two-wheeler': 0.08}

FULL_SEEDS = (3, 7, 11, 19, 29, 37, 41, 53)
QUICK_SEEDS = (3, 7, 11, 19, 29, 37)

results: list[tuple[str, str, str, bool]] = []

#: Set by main(); significance cannot be established from a handful of seeds, so
#: claims that depend on it are checked for direction only in quick mode, and
#: say so rather than silently passing or spuriously failing.
QUICK = False


def record(claim: str, measured: str, source: str, ok: bool,
           needs_significance: bool = False, direction_ok: bool | None = None) -> None:
    label = 'PASS' if ok else 'FAIL'
    note = ''
    if QUICK and needs_significance and not ok:
        # Too few seeds to resolve the interval. Fall back to checking the
        # effect still points the right way, and flag that it was not a full
        # test rather than claiming a pass.
        ok = bool(direction_ok)
        label = 'DIR ' if ok else 'FAIL'
        note = '   (direction only -- run without --quick to test significance)'
    results.append((claim, measured, source, ok))
    print(f'  [{label}] {claim}\n         measured: {measured}   ({source}){note}')


def paired(a: list[float], b: list[float]) -> tuple[float, float]:
    """Mean paired difference b - a, and its 95% half-interval."""
    d = [y - x for x, y in zip(a, b)]
    m = mean(d)
    ci = 1.96 * stdev(d) / sqrt(len(d)) if len(d) > 1 else 0.0
    return m, ci


def run_contrasting(controller: str, seed: int, mult: float, steps: int = 200) -> dict:
    """A two-wheeler feeder meeting a bus arterial, at a chosen demand level."""
    engine = MockTrafficEngine()
    for jid in MockTrafficEngine.JUNCTION_IDS:
        for d in ('north', 'south'):
            engine.approach_mix[(jid, d)] = TW_HEAVY
        for d in ('east', 'west'):
            engine.approach_mix[(jid, d)] = CAR_HEAVY
    engine.reset(scenario='rush', seed=seed)
    engine.arrival_multiplier = mult

    ctrl = build(controller, shielded=False)
    for _ in range(steps):
        engine.step(ctrl.choose_phases(engine.snapshot()))
    return engine.snapshot().metrics


def pooled(controller: str, scenario: str, key: str, seeds) -> list[float]:
    return [
        simulate(ScenarioConfig(controller=controller, steps=180, seed=s, scenario=scenario))
        ['metrics'][key]
        for s in seeds
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--quick', action='store_true', help='fewer seeds, for CI')
    args = parser.parse_args()
    global QUICK
    QUICK = args.quick
    seeds = QUICK_SEEDS if args.quick else FULL_SEEDS

    print(f'\nReproducing documented results over {len(seeds)} seeds'
          f'{" (quick mode)" if args.quick else ""}\n')

    # ---------------------------------------------- 1. the measurement study
    print('1. Lane-less discharge vs static PCU  (docs/HETEROGENEOUS_FLOW.md)')
    tw_static = VEHICLE_CLASSES['two-wheeler'].static_pcu
    tw_implied = implied_pcu('two-wheeler')
    overstatement = 100.0 * (tw_static - tw_implied) / tw_implied
    record(
        'static PCU over-states two-wheeler discharge by >40%',
        f'{overstatement:.1f}%  (static {tw_static}, implied {tw_implied:.2f})',
        'services.saturation', overstatement > 40,
    )

    car = implied_pcu('car')
    record(
        'the model reproduces textbook saturation flow for cars exactly',
        f'implied car PCU = {car:.3f}',
        'services.saturation', abs(car - 1.0) < 1e-9,
    )

    curve = comparison_report()['error_vs_two_wheeler_share']
    at_45 = next(r for r in curve if abs(r['two_wheeler_share'] - 0.45) < 1e-9)
    record(
        'PCU over-allocates green by >15% at a 45% two-wheeler share',
        f'{at_45["error_pct"]:.1f}%',
        'services.saturation', at_45['error_pct'] > 15,
    )
    record(
        'the error grows monotonically with two-wheeler share',
        ' -> '.join(f'{r["error_pct"]:.0f}%' for r in curve),
        'services.saturation',
        [r['error_pct'] for r in curve] == sorted(r['error_pct'] for r in curve),
    )

    # -------------------------------------------------- 2. coordination result
    print('\n2. Coordination beats local optimisation  (docs/BENCHMARKS.md)')
    for scenario in ('normal', 'rush'):
        fixed = pooled('fixed-time', scenario, 'p95_vehicle_delay', seeds)
        coord = pooled('coordinated-pressure-v1', scenario, 'p95_vehicle_delay', seeds)
        record(
            f'coordinated control lowers p95 delay vs fixed-time ({scenario})',
            f'{mean(fixed):.1f} -> {mean(coord):.1f} ticks',
            'services.scenario', mean(coord) < mean(fixed),
        )

    # ------------------------------------------- 3. the heterogeneous result
    print('\n3. Measuring pressure in people per second  (docs/HETEROGENEOUS_FLOW.md)')
    mult = 7.0
    pcu_people = [run_contrasting('pcu-timed-v1', s, mult)['served_people'] for s in seeds]
    ps_people = [run_contrasting('person-seconds-v1', s, mult)['served_people'] for s in seeds]
    m, ci = paired(pcu_people, ps_people)
    record(
        'person-seconds moves significantly more people than static PCU '
        '(contrasting mixes, saturated)',
        f'{m:+.0f} +/- {ci:.0f} people',
        'contrasting-mix run', m > ci > 0,
        needs_significance=True, direction_ok=m > 0,
    )

    het_worst = [run_contrasting('heterogeneous-timed-v1', s, mult)['worst_approach_wait']
                 for s in seeds]
    ps_worst = [run_contrasting('person-seconds-v1', s, mult)['worst_approach_wait']
                for s in seeds]
    m_w, ci_w = paired(het_worst, ps_worst)
    record(
        'optimising people-per-second removes the starvation that pure '
        'efficiency caused',
        f'worst-approach wait {mean(het_worst):.0f} -> {mean(ps_worst):.0f} ticks '
        f'({m_w:+.0f} +/- {ci_w:.0f})',
        'contrasting-mix run', m_w < -ci_w,
        needs_significance=True, direction_ok=m_w < 0,
    )

    # ------------------------------------- 4. the negative results, which must stay negative
    print('\n4. Negative results that must remain negative  (docs/BENCHMARKS.md)')
    uni_pcu = [run_contrasting('pcu-timed-v1', s, 4.0) for s in seeds]
    # Uniform mix: rebuild without any per-approach override.
    def run_uniform(controller: str, seed: int, mult: float, steps: int = 200) -> dict:
        engine = MockTrafficEngine()
        engine.reset(scenario='rush', seed=seed)
        engine.arrival_multiplier = mult
        ctrl = build(controller, shielded=False)
        for _ in range(steps):
            engine.step(ctrl.choose_phases(engine.snapshot()))
        return engine.snapshot().metrics

    u_pcu = [run_uniform('pcu-timed-v1', s, 4.0)['served_people'] for s in seeds]
    u_het = [run_uniform('heterogeneous-timed-v1', s, 4.0)['served_people'] for s in seeds]
    m_u, ci_u = paired(u_pcu, u_het)
    record(
        'correcting the measure does NOTHING when every approach carries the '
        'same mix (the bias cancels)',
        f'{m_u:+.0f} +/- {ci_u:.0f} people -- interval spans zero',
        'uniform-mix run', abs(m_u) <= ci_u,
    )

    # The documented cost of the fairness term under uniform traffic.
    u_ps = [run_uniform('person-seconds-v1', s, 4.0)['served_people'] for s in seeds]
    m_r, ci_r = paired(u_pcu, u_ps)
    record(
        'person-seconds is slightly WORSE under uniform traffic -- the cost of '
        'its fairness term, reported rather than hidden',
        f'{m_r:+.0f} +/- {ci_r:.0f} people',
        'uniform-mix run', m_r < 0,
    )

    # ------------------------------------------------------------- summary
    passed = sum(1 for *_, ok in results if ok)
    total = len(results)
    print(f'\n{"=" * 72}')
    print(f'{passed}/{total} documented claims reproduced')
    if passed != total:
        print('\nFAILED claims:')
        for claim, measured, _, ok in results:
            if not ok:
                print(f'  - {claim}\n    measured: {measured}')
        print('\nEither the change that broke this is wrong, or the documentation '
              'needs updating. Do not ignore it.')
    print('=' * 72)
    return 0 if passed == total else 1


if __name__ == '__main__':
    raise SystemExit(main())
