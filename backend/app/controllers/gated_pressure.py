"""Capacity-aware control for the oversaturated regime.

Classical max-pressure balances queues. That is the right objective when the
network has spare capacity, but it is the wrong one once every approach is
saturated, and the benchmark showed it: under heavy demand the pressure
controllers were all beaten by a plain fixed clock.

The reason is that pressure is a *difference* of queue lengths, so a controller
maximising it will happily spend green on a movement whose downstream link is
already full. Those vehicles cannot go anywhere. The green is spent, the queue
is rearranged, and nothing leaves the network.

This controller scores a phase by the traffic it can actually discharge:

    useful(movement) = min(queue, green capacity, space left downstream)

A movement that exits the network is never storage-limited, so it always scores
its full discharge -- which is what makes this controller keep throughput up
when the interior of the network is jammed. A small pressure term is retained so
that, when nothing is blocked, it behaves like a conventional pressure
controller rather than an arbitrary one.
"""

from __future__ import annotations

from app.controllers.base import Controller
from app.controllers.network_max_pressure import NetworkMaxPressureController
from app.models import NetworkSnapshot, Phase
from app.simulation.mock_engine import BASE_CAPACITY, LINK_STORAGE


class GatedPressureController(Controller):
    """Serve whichever phase moves the most vehicles that can actually move."""

    name = 'gated-pressure-v1'

    def __init__(
        self,
        pressure_weight: float = 0.25,
        switch_penalty: float = 1.0,
        capacity: int = BASE_CAPACITY,
        storage: int = LINK_STORAGE,
    ):
        #: How much conventional queue pressure still counts once nothing is
        #: blocked. Low, because useful discharge is the primary objective.
        self.pressure_weight = pressure_weight
        self.switch_penalty = switch_penalty
        self.capacity = capacity
        self.storage = storage
        self.transfers = NetworkMaxPressureController.TRANSFERS
        self.previous_phase: dict[str, Phase] = {}

    def _useful_discharge(self, junction, by_id, direction: str) -> float:
        """Vehicles this movement could really release this tick."""
        queue = float(getattr(junction, direction))
        target = self.transfers.get((junction.id, direction))
        if target is None:
            # Leaves the network: only queue and green capacity bind.
            room = float('inf')
        else:
            downstream = by_id.get(target[0])
            room = self.storage - float(getattr(downstream, target[1])) if downstream else 0.0
        return max(0.0, min(queue, float(self.capacity), room))

    def _pressure(self, junction, by_id, direction: str) -> float:
        queue = float(getattr(junction, direction))
        target = self.transfers.get((junction.id, direction))
        if target is None:
            return queue
        downstream = by_id.get(target[0])
        return queue - (float(getattr(downstream, target[1])) if downstream else 0.0)

    def choose_phases(self, snapshot: NetworkSnapshot) -> dict[str, Phase]:
        by_id = {j.id: j for j in snapshot.junctions}
        actions: dict[str, Phase] = {}

        for j in snapshot.junctions:
            scores: dict[str, float] = {'NS': 0.0, 'EW': 0.0}
            for phase, directions in (('NS', ('north', 'south')), ('EW', ('east', 'west'))):
                for direction in directions:
                    scores[phase] += self._useful_discharge(j, by_id, direction)
                    scores[phase] += self.pressure_weight * self._pressure(j, by_id, direction)
                if self.previous_phase.get(j.id) not in (None, phase):
                    scores[phase] -= self.switch_penalty
            actions[j.id] = 'NS' if scores['NS'] >= scores['EW'] else 'EW'

        self.previous_phase = actions.copy()
        return actions
