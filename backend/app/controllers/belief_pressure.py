"""Signal control that knows what it does not know.

Every controller in this project, and effectively every one in the literature,
treats the number coming off a detector as the truth. That assumption is
harmless in a simulator where the count is exact. It is not harmless on an
Indian arterial at 8pm in the rain, where a camera is counting overlapping
two-wheelers through glare.

The failure it causes is specific and bad. When a detector drops out it reports
**zero**, and zero is indistinguishable from an empty approach. A pressure
controller sees no demand, never serves that road, and the queue grows without
bound behind a sensor nobody knows is broken. The safety shield eventually
forces a switch on maximum green, but only after the damage.

This controller keeps a *belief* about each approach instead of a reading:

    predict   x̂ ← x̂ + arrivals − discharge      (what the model expects)
    update    x̂ ← x̂ + K(z − x̂),  K = P/(P+R)   (what the camera saw)

``R`` is the measurement variance, derived from the confidence the detector
reports. A trusted reading has small ``R`` and dominates; an untrusted one
barely moves the belief. ``P`` is how unsure we are, and it **grows every tick
an approach goes unobserved**.

Decisions are then made on the *upper confidence bound*, ``x̂ + κ√P``, not on
``x̂``. That single choice is what fixes the dropout failure: an approach we
cannot see is treated as potentially long rather than definitely empty, so it
keeps getting served while the belief says it might be backing up. Optimism
would be the wrong direction here -- the costly error is assuming a road is
clear when it is full, not the reverse.
"""

from __future__ import annotations

from app.controllers.base import Controller
from app.controllers.network_max_pressure import NetworkMaxPressureController
from app.models import NetworkSnapshot, Phase

PHASES: tuple[Phase, Phase] = ('NS', 'EW')
PHASE_DIRECTIONS = {'NS': ('north', 'south'), 'EW': ('east', 'west')}
ALL_DIRECTIONS = ('north', 'south', 'east', 'west')


class BeliefPressureController(Controller):
    """Coordinated pressure control over a filtered belief, not a raw reading."""

    name = 'belief-pressure-v1'

    def __init__(
        self,
        deviation_threshold: float = 8.0,
        caution: float = 1.4,
        process_noise: float = 2.0,
        discharge_rate: float = 5.0,
        arrival_memory: float = 0.15,
    ):
        self.deviation_threshold = deviation_threshold
        #: How many standard deviations of caution to add. 0 trusts the mean
        #: estimate; higher hedges harder against an approach being worse than
        #: it looks. This is the whole safety margin, so it is one number and
        #: it is named.
        self.caution = caution
        #: How fast certainty decays while an approach goes unobserved.
        self.process_noise = process_noise
        self.discharge_rate = discharge_rate
        self.arrival_memory = arrival_memory
        self.transfers = NetworkMaxPressureController.TRANSFERS

        self.estimate: dict[tuple[str, str], float] = {}
        self.variance: dict[tuple[str, str], float] = {}
        self.arrival_rate: dict[tuple[str, str], float] = {}
        self.last_served: dict[tuple[str, str], bool] = {}

    # ------------------------------------------------------------- filtering

    def _measurement_variance(self, confidence: float) -> float:
        """Turn a confidence score into how much to distrust the reading."""
        c = max(0.02, min(1.0, confidence))
        # Perfect confidence -> near-zero variance, so the reading wins.
        # Zero confidence -> enormous variance, so the reading is ignored.
        return ((1.0 - c) / c) ** 2 * 4.0 + 0.25

    def _observe(self, snapshot: NetworkSnapshot) -> None:
        for j in snapshot.junctions:
            for direction in ALL_DIRECTIONS:
                key = (j.id, direction)
                reading = float(getattr(j, direction))
                confidence = float((j.confidence or {}).get(direction, 1.0))

                if key not in self.estimate:
                    self.estimate[key] = reading
                    self.variance[key] = 1.0
                    self.arrival_rate[key] = 1.5
                    self.last_served[key] = False
                    continue

                # --- predict: where the model thinks the queue went ---------
                served = self.last_served.get(key, False)
                predicted = self.estimate[key] + self.arrival_rate[key]
                if served:
                    predicted -= self.discharge_rate
                predicted = max(0.0, predicted)
                self.variance[key] += self.process_noise

                # --- update: fold in what the detector claims to see --------
                r = self._measurement_variance(confidence)
                gain = self.variance[key] / (self.variance[key] + r)
                innovation = reading - predicted
                self.estimate[key] = max(0.0, predicted + gain * innovation)
                self.variance[key] = max(0.05, (1.0 - gain) * self.variance[key])

                # Learn how fast this approach fills, but only from readings
                # worth learning from.
                if not served and confidence > 0.5:
                    observed_growth = max(0.0, innovation + self.arrival_rate[key])
                    self.arrival_rate[key] += self.arrival_memory * (
                        observed_growth - self.arrival_rate[key])
                    self.arrival_rate[key] = min(12.0, max(0.0, self.arrival_rate[key]))

    def _upper_bound(self, key: tuple[str, str]) -> float:
        """The queue could plausibly be this long. Act on this, not the mean."""
        return self.estimate.get(key, 0.0) + self.caution * (self.variance.get(key, 1.0) ** 0.5)

    # ---------------------------------------------------------------- decide

    def _junction_score(self, junction, phase: Phase) -> float:
        return sum(self._upper_bound((junction.id, d)) for d in PHASE_DIRECTIONS[phase])

    def choose_phases(self, snapshot: NetworkSnapshot) -> dict[str, Phase]:
        self._observe(snapshot)

        network = {
            phase: sum(self._junction_score(j, phase) for j in snapshot.junctions)
            for phase in PHASES
        }
        common: Phase = 'NS' if network['NS'] >= network['EW'] else 'EW'
        other: Phase = 'EW' if common == 'NS' else 'NS'

        actions: dict[str, Phase] = {}
        for j in snapshot.junctions:
            local_common = self._junction_score(j, common)
            local_other = self._junction_score(j, other)
            deviate = (local_other - local_common) > self.deviation_threshold
            actions[j.id] = other if deviate else common

        for jid, phase in actions.items():
            served = PHASE_DIRECTIONS.get(phase, ())
            for direction in ALL_DIRECTIONS:
                self.last_served[(jid, direction)] = direction in served
        return actions

    # ----------------------------------------------------------------- audit

    def explain(self, snapshot: NetworkSnapshot) -> dict:
        """Belief against reading, so the divergence is inspectable."""
        rows = []
        for j in snapshot.junctions:
            for direction in ALL_DIRECTIONS:
                key = (j.id, direction)
                rows.append({
                    'approach': f'{j.id}-{direction}',
                    'reading': getattr(j, direction),
                    'confidence': round(float((j.confidence or {}).get(direction, 1.0)), 3),
                    'belief': round(self.estimate.get(key, 0.0), 2),
                    'uncertainty': round(self.variance.get(key, 0.0) ** 0.5, 2),
                    'acts_on': round(self._upper_bound(key), 2),
                })
        return {
            'measure': 'upper confidence bound on queue length',
            'caution_sigmas': self.caution,
            'approaches': rows,
            'reading': (
                'Where acts_on far exceeds reading, the controller is refusing to '
                'believe an approach is as empty as its detector claims.'
            ),
        }
