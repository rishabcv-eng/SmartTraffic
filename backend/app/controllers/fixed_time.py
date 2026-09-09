from app.controllers.base import Controller
from app.models import NetworkSnapshot, Phase


class FixedTimeController(Controller):
    """Conventional fixed-clock signal: equal green windows regardless of demand.

    This is the baseline almost every Indian junction runs today, and the
    reference every other controller here is measured against. It also doubles
    as the fallback plan the safety shield reverts to when detection or
    communication fails.
    """

    name = 'fixed-time'

    def __init__(self, cycle: int = 8):
        self.cycle = cycle

    def choose_phases(self, snapshot: NetworkSnapshot) -> dict[str, Phase]:
        phase: Phase = 'NS' if (snapshot.tick // self.cycle) % 2 == 0 else 'EW'
        return {j.id: phase for j in snapshot.junctions}
