from __future__ import annotations

from app.controllers.base import Controller
from app.controllers.network_max_pressure import NetworkMaxPressureController
from app.models import NetworkSnapshot, Phase


class TransitPriorityController(Controller):
    """Network pressure measured in people rather than vehicles.

    Optimising vehicle throughput quietly favours private cars: a bus carrying
    35 passengers counts exactly as much as one car carrying 1.5. This
    controller scores each phase by person-pressure instead, so a loaded bus
    approach outranks a longer queue of single-occupancy cars.

    It keeps the network-aware structure of max-pressure -- upstream demand
    minus the downstream approach that would receive the discharge -- so it
    still refuses to push traffic into a blocked link.
    """

    name = 'transit-priority-v1'

    def __init__(self, bus_weight: float = 1.0, switch_penalty: float = 1.5):
        #: Scales how strongly bus occupancy dominates. 1.0 uses raw occupancy.
        self.bus_weight = bus_weight
        self.switch_penalty = switch_penalty
        self.previous_phase: dict[str, Phase] = {}
        self.transfers = NetworkMaxPressureController.TRANSFERS

    def _person_load(self, junction, direction: str) -> float:
        from app.models import OCCUPANCY

        buses = junction.buses.get(direction, 0)
        cars = max(0, getattr(junction, direction) - buses)
        return cars * OCCUPANCY['car'] + buses * OCCUPANCY['bus'] * self.bus_weight

    def choose_phases(self, snapshot: NetworkSnapshot) -> dict[str, Phase]:
        by_id = {j.id: j for j in snapshot.junctions}
        actions: dict[str, Phase] = {}

        for j in snapshot.junctions:
            scores: dict[str, float] = {'NS': 0.0, 'EW': 0.0}
            for phase, directions in (('NS', ('north', 'south')), ('EW', ('east', 'west'))):
                for direction in directions:
                    upstream = self._person_load(j, direction)
                    target = self.transfers.get((j.id, direction))
                    downstream = (
                        0.0 if target is None
                        else self._person_load(by_id[target[0]], target[1])
                    )
                    scores[phase] += upstream - downstream
                if self.previous_phase.get(j.id) not in (None, phase):
                    scores[phase] -= self.switch_penalty
            actions[j.id] = 'NS' if scores['NS'] >= scores['EW'] else 'EW'

        self.previous_phase = actions.copy()
        return actions
