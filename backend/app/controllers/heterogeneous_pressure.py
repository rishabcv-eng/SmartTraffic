"""Pressure measured in discharge-seconds, not vehicles or PCU.

This is the one idea in the project that is not standard practice.

Every controller here, and most in the literature, measures the pressure on an
approach as a *count* of vehicles, or converts the mix to car equivalents with
a static PCU factor. Both are wrong in the same direction on Indian roads, for
the same reason: they answer "how much traffic is waiting" when the question a
signal controller actually faces is "how long would it take to clear".

Those differ sharply once lane discipline goes. Two-wheelers filter forward
into lateral gaps and discharge two or three abreast inside one nominal lane,
so a queue of thirty two-wheelers clears in roughly a third of the time a queue
of thirty cars needs. A count-based controller cannot see the difference at
all. A static-PCU controller sees some of it, but PCU factors are calibrated
for space occupancy in *moving* flow, not for discharge headway at a stop line,
and they over-state two-wheelers by around 55% on the defaults used here.

So this controller scores a phase by the green time its queues physically need
(``services.saturation``), capped by the green actually available and by room
on the receiving link. Everything else -- the network-level phase selection and
the high bar for a junction to break ranks -- is inherited unchanged from
``coordinated-pressure-v1``, so any difference measured against it is
attributable to the change of measure alone.

``PCUPressureController`` is included as the honest baseline: it is what a
conventional adaptive system in an Indian city would do today, and it is the
controller this work has to beat to mean anything.
"""

from __future__ import annotations

from app.controllers.base import Controller
from app.controllers.network_max_pressure import NetworkMaxPressureController
from app.models import NetworkSnapshot, Phase
from app.services.saturation import (
    DEFAULT_LANES,
    VEHICLE_CLASSES,
    discharge_seconds,
)
from app.simulation.mock_engine import LINK_STORAGE, TICK_SECONDS

PHASES: tuple[Phase, Phase] = ('NS', 'EW')
PHASE_DIRECTIONS = {'NS': ('north', 'south'), 'EW': ('east', 'west')}


class MeasuredPressureController(Controller):
    """Coordinated control, with the measure of pressure left abstract.

    Subclasses decide what a queue is *worth*; the coordination logic is shared
    so that comparing them isolates the measurement.
    """

    name = 'measured-pressure'

    #: Green available per tick, in whatever unit the subclass measures in.
    capacity = TICK_SECONDS

    def __init__(self, deviation_threshold: float = 8.0, pressure_weight: float = 0.25):
        self.deviation_threshold = deviation_threshold
        self.pressure_weight = pressure_weight
        self.transfers = NetworkMaxPressureController.TRANSFERS

    # ----------------------------------------------------------- measurement

    def _demand(self, junction, direction: str) -> float:
        raise NotImplementedError

    def _room(self, junction, by_id, direction: str) -> float:
        """Room on the receiving link, in the same unit as demand."""
        target = self.transfers.get((junction.id, direction))
        if target is None:
            return float('inf')
        downstream = by_id.get(target[0])
        if downstream is None:
            return 0.0
        # Storage is in car-lengths; a car costs one car-length and one unit of
        # discharge, so the two scales coincide for the receiving link.
        occupied = self._demand(downstream, target[1])
        return max(0.0, LINK_STORAGE - occupied)

    def _junction_score(self, junction, by_id, phase: Phase) -> float:
        score = 0.0
        for direction in PHASE_DIRECTIONS[phase]:
            demand = self._demand(junction, direction)
            useful = max(0.0, min(demand, self.capacity, self._room(junction, by_id, direction)))
            score += useful + self.pressure_weight * demand
        return score

    # ---------------------------------------------------------------- decide

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


class HeterogeneousPressureController(MeasuredPressureController):
    """Pressure as the green time a mixed queue physically needs."""

    name = 'heterogeneous-pressure-v1'

    def __init__(self, deviation_threshold: float = 4.0, pressure_weight: float = 0.25,
                 lanes: float = DEFAULT_LANES):
        super().__init__(deviation_threshold, pressure_weight)
        self.lanes = lanes

    def _demand(self, junction, direction: str) -> float:
        counts = junction.composition.get(direction)
        if not counts:
            return float(getattr(junction, direction)) * discharge_seconds('car', self.lanes)
        return sum(n * discharge_seconds(k, self.lanes) for k, n in counts.items())

    def explain(self, snapshot: NetworkSnapshot) -> dict:
        """What the controller saw, against what a PCU controller would have."""
        rows = []
        for j in snapshot.junctions:
            for phase in PHASES:
                seconds = j.discharge_pressure(phase, self.lanes)
                pcu = j.pcu_pressure(phase)
                rows.append({
                    'junction': j.id,
                    'phase': phase,
                    'vehicles': j.pressure_ns if phase == 'NS' else j.pressure_ew,
                    'pcu_belief': round(pcu, 2),
                    'green_seconds_needed': round(seconds, 2),
                    'pcu_overstatement_pct': round(
                        100.0 * (pcu * discharge_seconds('car', self.lanes) - seconds)
                        / max(1e-9, seconds), 1),
                })
        return {'measure': 'discharge-seconds', 'lanes': self.lanes, 'approaches': rows}


class PCUPressureController(MeasuredPressureController):
    """Conventional baseline: pressure as a static-PCU sum.

    This is what an adaptive system deployed in an Indian city does today, and
    the controller the heterogeneous measure has to beat.
    """

    name = 'pcu-pressure-v1'

    #: One PCU per second of green at saturation flow, so a tick of green is
    #: worth TICK_SECONDS PCU. Expressed separately to keep the unit honest.
    capacity = TICK_SECONDS

    def __init__(self, deviation_threshold: float = 4.0, pressure_weight: float = 0.25):
        super().__init__(deviation_threshold, pressure_weight)

    def _demand(self, junction, direction: str) -> float:
        counts = junction.composition.get(direction)
        if not counts:
            return float(getattr(junction, direction))
        return sum(n * VEHICLE_CLASSES[k].static_pcu for k, n in counts.items())


class TimedPressureController(MeasuredPressureController):
    """Allocate green *duration*, not just phase order.

    The first version of this experiment came back inside the noise, and the
    reason was structural rather than a failure of the idea. Choosing between
    NS and EW is a binary decision, and re-scaling both sides of a comparison
    by a systematic factor seldom flips which side is larger. The measure
    changed the magnitudes and almost never changed the argmax.

    But green *duration* is where a mis-measured queue actually costs
    something. A controller that holds a phase for as long as it believes the
    queue needs will, if it over-states a two-wheeler queue by a fifth, hold
    that approach green for a fifth longer than the traffic requires -- and
    every one of those seconds is taken from the cross street while the
    approach it was given to stands empty.

    So this controller commits to a phase for the time its queues need, and
    subclasses differ only in how they estimate that time.
    """

    name = 'timed-pressure'

    def __init__(self, deviation_threshold: float = 4.0, pressure_weight: float = 0.25,
                 min_green: int = 2, max_green: int = 14):
        super().__init__(deviation_threshold, pressure_weight)
        self.min_green = min_green
        self.max_green = max_green
        self.committed: Phase | None = None
        self.remaining = 0

    def _needed_ticks(self, snapshot: NetworkSnapshot, phase: Phase) -> int:
        """How many ticks of green the network believes this phase needs."""
        demand = sum(
            sum(self._demand(j, d) for d in PHASE_DIRECTIONS[phase])
            for j in snapshot.junctions
        )
        # Capacity is per approach per tick; the network serves two approaches
        # per junction at once, so normalise by that to get a duration.
        per_tick = self.capacity * 2 * max(1, len(snapshot.junctions))
        ticks = int(round(demand / max(1e-9, per_tick)))
        return max(self.min_green, min(self.max_green, ticks))

    def choose_phases(self, snapshot: NetworkSnapshot) -> dict[str, Phase]:
        if self.committed is None or self.remaining <= 0:
            by_id = {j.id: j for j in snapshot.junctions}
            scores = {
                p: sum(self._junction_score(j, by_id, p) for j in snapshot.junctions)
                for p in PHASES
            }
            chosen: Phase = 'NS' if scores['NS'] >= scores['EW'] else 'EW'
            self.committed = chosen
            self.remaining = self._needed_ticks(snapshot, chosen)

        self.remaining -= 1
        return {j.id: self.committed for j in snapshot.junctions}


class HeterogeneousTimedController(TimedPressureController, HeterogeneousPressureController):
    """Green duration set by the time a mixed queue physically needs."""

    name = 'heterogeneous-timed-v1'

    def __init__(self, **kwargs):
        lanes = kwargs.pop('lanes', DEFAULT_LANES)
        TimedPressureController.__init__(self, **kwargs)
        self.lanes = lanes


class PCUTimedController(TimedPressureController, PCUPressureController):
    """Green duration set by a static-PCU estimate. The conventional baseline."""

    name = 'pcu-timed-v1'


class PersonSecondsController(TimedPressureController):
    """Maximise people moved per second of green, with an explicit fairness term.

    ``heterogeneous-timed-v1`` corrected the measurement and moved many more
    people, but the way it did so was uncomfortable. It optimises *road
    efficiency* -- green time per vehicle cleared -- and because two-wheelers
    are cheap to clear, an approach full of them scores low on the thing the
    controller actually maximises. Green drifted to the arterial, and the 95th
    percentile delay on the two-wheeler feeder rose by 48 ticks at demand x4.
    In an Indian city those riders are generally the least able to absorb it.

    The mistake was optimising a proxy. Road efficiency is not the objective; it
    is a constraint. What a signal should maximise is *people moved*, and the
    quantity that follows from that is people per second of green:

        rate_i = (people waiting on approach i) / (green seconds approach i needs)

    A two-wheeler queue scores well here despite carrying few people each,
    precisely because it clears so fast. A bus queue scores well because each
    vehicle carries thirty-five. The previous controller could only see the
    denominator.

    On top of that sits a fairness term proportional to accumulated red time, so
    an approach that has been waiting gains priority when the choice is close.
    That is what keeps the person-throughput gain from being paid for by one
    group of road users.
    """

    name = 'person-seconds-v1'

    def __init__(self, fairness_weight: float = 1.6, lanes: float = DEFAULT_LANES, **kwargs):
        super().__init__(**kwargs)
        self.lanes = lanes
        #: People-equivalents each tick of accumulated red is worth. Raising it
        #: buys a shorter tail of long waits with a little person-throughput.
        self.fairness_weight = fairness_weight
        self.red_ticks: dict[tuple[str, str], int] = {}

    # Duration and downstream room stay in seconds, which is the unit they are
    # physically measured in; only the *objective* changes.
    def _demand(self, junction, direction: str) -> float:
        counts = junction.composition.get(direction)
        if not counts:
            return float(getattr(junction, direction)) * discharge_seconds('car', self.lanes)
        return sum(n * discharge_seconds(k, self.lanes) for k, n in counts.items())

    def _people(self, junction, direction: str) -> float:
        counts = junction.composition.get(direction)
        if not counts:
            return float(getattr(junction, direction)) * VEHICLE_CLASSES['car'].occupancy
        return sum(n * VEHICLE_CLASSES[k].occupancy for k, n in counts.items())

    def _junction_score(self, junction, by_id, phase: Phase) -> float:
        score = 0.0
        for direction in PHASE_DIRECTIONS[phase]:
            seconds = self._demand(junction, direction)
            if seconds <= 0:
                continue
            people = self._people(junction, direction)
            room = self._room(junction, by_id, direction)
            # Green actually usable this tick, capped by capacity and by room
            # on the receiving link.
            usable = max(0.0, min(seconds, self.capacity, room))
            # People that green would actually move.
            score += people * (usable / seconds)
            score += self.fairness_weight * self.red_ticks.get((junction.id, direction), 0)
        return score

    def choose_phases(self, snapshot: NetworkSnapshot) -> dict[str, Phase]:
        actions = super().choose_phases(snapshot)
        for jid, phase in actions.items():
            served = PHASE_DIRECTIONS.get(phase, ())
            for direction in ('north', 'south', 'east', 'west'):
                key = (jid, direction)
                self.red_ticks[key] = 0 if direction in served else self.red_ticks.get(key, 0) + 1
        return actions
