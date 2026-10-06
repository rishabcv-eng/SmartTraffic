"""Coordinated capacity-aware control: the answer to the oversaturation result.

The benchmark threw up an uncomfortable result: every locally-optimal adaptive
controller was beaten by a plain fixed clock, and the effect got worse as demand
rose. Adding realistic link storage shrank the gap but did not close it.

The cause turned out not to be the objective at all. A fixed clock switches
every junction *in unison*, which accidentally implements a green wave along
this network's platoon chains -- a vehicle discharged by J1 arrives at J3 to
find the same phase still running. Controllers that optimise each junction
independently maximise local pressure and destroy that alignment, so platoons
stop at every junction and the network loses more to stopping than local
optimisation ever wins back.

So this controller optimises the *network's* phase, not each junction's:

1. Score both global phases by the useful discharge they would produce summed
   over every junction, where useful discharge is capped by green capacity and
   by the space left on the receiving link.
2. Adopt that phase everywhere, preserving progression by construction.
3. Allow a single junction to break ranks only when its local case is
   overwhelming -- a badly starved or badly blocked approach -- so the
   controller stays adaptive without dissolving back into local greed.

Step 3 is what separates this from a fixed clock: coordination is the default,
not the rule.
"""

from __future__ import annotations

from app.controllers.base import Controller
from app.controllers.network_max_pressure import NetworkMaxPressureController
from app.models import NetworkSnapshot, Phase
from app.simulation.mock_engine import BASE_CAPACITY, LINK_STORAGE

PHASES: tuple[Phase, Phase] = ('NS', 'EW')
PHASE_DIRECTIONS = {'NS': ('north', 'south'), 'EW': ('east', 'west')}


class CoordinatedPressureController(Controller):
    """Network-level phase selection with a high bar for local deviation."""

    name = 'coordinated-pressure-v1'

    def __init__(
        self,
        deviation_threshold: float = 8.0,
        pressure_weight: float = 0.25,
        capacity: int = BASE_CAPACITY,
        storage: int = LINK_STORAGE,
    ):
        #: How much better a junction's local case must be, in vehicles of
        #: useful discharge, before it is allowed to break the network phase.
        #: Set this to 0 and the controller degenerates into local greed;
        #: set it very high and it becomes a fixed clock with adaptive timing.
        self.deviation_threshold = deviation_threshold
        self.pressure_weight = pressure_weight
        self.capacity = capacity
        self.storage = storage
        self.transfers = NetworkMaxPressureController.TRANSFERS

    def _useful_discharge(self, junction, by_id, direction: str) -> float:
        queue = float(getattr(junction, direction))
        target = self.transfers.get((junction.id, direction))
        if target is None:
            room = float('inf')      # leaves the network; never storage-limited
        else:
            downstream = by_id.get(target[0])
            room = self.storage - float(getattr(downstream, target[1])) if downstream else 0.0
        return max(0.0, min(queue, float(self.capacity), room))

    def _junction_score(self, junction, by_id, phase: Phase) -> float:
        score = 0.0
        for direction in PHASE_DIRECTIONS[phase]:
            score += self._useful_discharge(junction, by_id, direction)
            score += self.pressure_weight * float(getattr(junction, direction))
        return score

    def choose_phases(self, snapshot: NetworkSnapshot) -> dict[str, Phase]:
        by_id = {j.id: j for j in snapshot.junctions}

        network = {
            phase: sum(self._junction_score(j, by_id, phase) for j in snapshot.junctions)
            for phase in PHASES
        }
        common: Phase = 'NS' if network['NS'] >= network['EW'] else 'EW'
        other: Phase = 'EW' if common == 'NS' else 'NS'

        actions: dict[str, Phase] = {}
        for j in snapshot.junctions:
            local_common = self._junction_score(j, by_id, common)
            local_other = self._junction_score(j, by_id, other)
            deviate = (local_other - local_common) > self.deviation_threshold
            actions[j.id] = other if deviate else common
        return actions

    def explain(self, snapshot: NetworkSnapshot) -> dict:
        """Network scores and which junctions broke ranks, for the audit trail."""
        by_id = {j.id: j for j in snapshot.junctions}
        network = {
            phase: round(sum(self._junction_score(j, by_id, phase) for j in snapshot.junctions), 2)
            for phase in PHASES
        }
        common: Phase = 'NS' if network['NS'] >= network['EW'] else 'EW'
        actions = self.choose_phases(snapshot)
        return {
            'network_scores': network,
            'network_phase': common,
            'deviating_junctions': [jid for jid, p in actions.items() if p != common],
            'deviation_threshold': self.deviation_threshold,
        }
