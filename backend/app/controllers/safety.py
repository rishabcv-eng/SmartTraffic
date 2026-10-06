"""Constraint and explanation layer that wraps any signal controller.

A traffic controller that a city can actually install has to answer three
questions that an optimiser alone cannot:

* **Is it safe and fair?** Minimum green, starvation limits and a guaranteed
  maximum pedestrian wait are hard constraints, not objectives to trade away.
* **What happens when it breaks?** Detector and comms failures must degrade to
  a known-good plan rather than to undefined behaviour.
* **Why did it do that?** Every phase change is logged with the pressures and
  the binding constraint, so an engineer can audit a decision after an incident.

The shield sits between the optimiser and the road. The optimiser *proposes*;
the shield *disposes*, and records the reason.
"""

from __future__ import annotations

from collections import deque

from app.controllers.base import Controller
from app.controllers.fixed_time import FixedTimeController
from app.models import NetworkSnapshot, Phase

#: Reasons a proposal was overridden, ordered by the priority they are applied.
REASONS = {
    'signal-fault': 'Signal head failed; fail-safe all-red flashing, no service commanded.',
    'comms-loss': 'Communication lost; junction cabinet running its own fixed clock.',
    'detector-fault-fallback': 'Detector unreliable; reverted to the time-of-day fixed plan.',
    'emergency-preemption': 'Priority vehicle approaching; corridor held green for it.',
    'pedestrian-max-wait': 'Pedestrian wait limit reached; exclusive crossing phase inserted.',
    'min-green-hold': 'Minimum green not yet elapsed; proposal deferred.',
    'max-green-starvation-guard': 'Maximum green exceeded; forced switch to protect the cross road.',
    'accepted': 'Proposal accepted; no constraint was binding.',
}


class SafetyShield(Controller):
    """Wrap a controller with safety, fairness, fallback and audit logging."""

    def __init__(
        self,
        controller: Controller,
        min_green: int = 3,
        max_green: int = 14,
        max_pedestrian_wait: int = 18,
        emergency_lead_ticks: int = 2,
        audit_length: int = 400,
    ):
        self.controller = controller
        self.min_green = min_green
        self.max_green = max_green
        self.max_pedestrian_wait = max_pedestrian_wait
        self.emergency_lead_ticks = emergency_lead_ticks
        self.fallback = FixedTimeController()
        self.phase_age: dict[str, int] = {}
        self.current: dict[str, Phase] = {}
        self.decisions: list[dict] = []
        self.audit: deque = deque(maxlen=audit_length)

    @property
    def name(self) -> str:
        return f'{self.controller.name}+shield'

    # ------------------------------------------------------------- preemption

    def _preempted_junctions(self, snapshot: NetworkSnapshot) -> dict[str, Phase]:
        """Junctions that must be held green for an active priority vehicle.

        The junction the vehicle is at is always preempted. The next junction on
        its route is preempted once the vehicle is within the lead window, which
        is what turns a series of local preemptions into a rolling green wave.
        """
        run = snapshot.emergency
        if not run or not run.get('active'):
            return {}

        route: list[str] = run.get('route') or []
        directions: list[str] = run.get('directions') or []
        current = run.get('at_junction')
        if current is None or current not in route:
            return {}

        index = route.index(current)
        held: dict[str, Phase] = {}
        for offset in (0, 1):
            pos = index + offset
            if pos >= len(route) or pos >= len(directions):
                break
            if offset == 1 and run.get('travel_remaining', 0) > self.emergency_lead_ticks:
                break
            approach = directions[pos]
            held[route[pos]] = 'NS' if approach in ('north', 'south') else 'EW'
        return held

    # ----------------------------------------------------------------- decide

    def choose_phases(self, snapshot: NetworkSnapshot) -> dict[str, Phase]:
        proposals = self.controller.choose_phases(snapshot)
        fallback_plan = self.fallback.choose_phases(snapshot)
        preempted = self._preempted_junctions(snapshot)

        actions: dict[str, Phase] = {}
        self.decisions = []

        for j in snapshot.junctions:
            proposed = proposals.get(j.id, j.phase)
            current = self.current.get(j.id, j.phase)
            age = self.phase_age.get(j.id, 0)
            reason = 'accepted'
            applied: Phase = proposed

            if j.mode == 'all-red-flash':
                applied, reason = current, 'signal-fault'
            elif j.mode == 'local-fallback':
                applied, reason = fallback_plan[j.id], 'comms-loss'
            elif j.mode == 'detector-degraded':
                applied, reason = fallback_plan[j.id], 'detector-fault-fallback'
            elif j.id in preempted:
                applied, reason = preempted[j.id], 'emergency-preemption'
            elif j.pedestrian > 0 and j.ped_wait >= self.max_pedestrian_wait:
                applied, reason = 'PED', 'pedestrian-max-wait'
            elif age >= self.max_green and proposed == current:
                applied = 'EW' if current == 'NS' else 'NS'
                reason = 'max-green-starvation-guard'
            elif proposed != current and age < self.min_green:
                applied, reason = current, 'min-green-hold'

            actions[j.id] = applied
            self.phase_age[j.id] = 0 if applied != current else age + 1
            self.current[j.id] = applied

            record = {
                'tick': snapshot.tick,
                'junction': j.id,
                'proposed': proposed,
                'applied': applied,
                'reason': reason,
                'explanation': REASONS[reason],
                'mode': j.mode,
                'phase_age': age,
                'pressure_ns': j.pressure_ns,
                'pressure_ew': j.pressure_ew,
                'person_pressure_ns': round(j.person_pressure('NS'), 1),
                'person_pressure_ew': round(j.person_pressure('EW'), 1),
                'pedestrians_waiting': j.pedestrian,
                'pedestrian_wait': j.ped_wait,
                'overridden': applied != proposed,
            }
            self.decisions.append(record)
            self.audit.append(record)

        return actions

    # ------------------------------------------------------------------ audit

    def recent_decisions(self, limit: int = 60, junction: str | None = None) -> list[dict]:
        rows = [r for r in self.audit if junction is None or r['junction'] == junction]
        return rows[-limit:]

    def override_summary(self) -> dict:
        """How often each constraint actually bound, over the audit window."""
        counts: dict[str, int] = {}
        for row in self.audit:
            counts[row['reason']] = counts.get(row['reason'], 0) + 1
        total = max(1, len(self.audit))
        return {
            'decisions_logged': len(self.audit),
            'counts': counts,
            'override_rate_pct': round(
                100.0 * sum(v for k, v in counts.items() if k != 'accepted') / total, 2
            ),
            'reasons': REASONS,
        }
