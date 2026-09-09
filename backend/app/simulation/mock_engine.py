from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass
from statistics import mean

from app.models import DIRECTIONS, OCCUPANCY, JunctionState, NetworkSnapshot, Phase
from app.simulation.base import TrafficEngine

#: Discharge capacity of one approach during one tick of green, in vehicle units.
BASE_CAPACITY = 5

#: A bus occupies more green time than a car (longer headway plus stop dwell).
BUS_SERVICE_COST = 2

#: Saturation-flow multipliers. Wet and low-visibility conditions measurably
#: reduce discharge rate; these follow the usual HCM-style adjustment range.
WEATHER_CAPACITY = {
    'clear': 1.0,
    'rain': 0.85,
    'heavy-rain': 0.70,
    'fog': 0.80,
}

#: Ticks a vehicle needs to travel from one junction to the next.
LINK_TRAVEL_TICKS = 4

#: How many vehicles one approach link can physically hold.
#:
#: This matters more than it looks. Without a storage limit, queues grow without
#: bound and a green can always discharge into a downstream link that is already
#: full -- which is not traffic, it is bookkeeping. Finite storage is also what
#: max-pressure control assumes: the pressure signal is only meaningful when a
#: blocked downstream link can actually refuse to accept more vehicles.
#:
#: 40 vehicles is roughly a 200 m two-lane approach at jam density.
LINK_STORAGE = 40


@dataclass
class Vehicle:
    """One queued road user. Tracking arrival ticks gives exact delay stats."""

    arrival_tick: int
    kind: str = 'car'

    @property
    def occupancy(self) -> float:
        return OCCUPANCY.get(self.kind, OCCUPANCY['car'])


@dataclass
class EmergencyRun:
    """A priority vehicle physically traversing the network."""

    vehicle_type: str
    route: list[str]
    directions: list[str]
    index: int = 0
    travel_remaining: int = 0
    start_tick: int = 0
    finish_tick: int | None = None
    delay_ticks: int = 0
    waiting: bool = False

    @property
    def at_junction(self) -> str | None:
        if self.finish_tick is not None or self.index >= len(self.route):
            return None
        return self.route[self.index]

    @property
    def approach(self) -> str | None:
        if self.finish_tick is not None or self.index >= len(self.directions):
            return None
        return self.directions[self.index]

    def to_dict(self) -> dict:
        return {
            'vehicle_type': self.vehicle_type,
            'route': self.route,
            'directions': self.directions,
            'at_junction': self.at_junction,
            'approach': self.approach,
            'travel_remaining': self.travel_remaining,
            'waiting_at_red': self.waiting,
            'delay_ticks': self.delay_ticks,
            'start_tick': self.start_tick,
            'finish_tick': self.finish_tick,
            'active': self.finish_tick is None,
        }


class MockTrafficEngine(TrafficEngine):
    """Deterministic four-junction traffic lab with queue propagation.

    It is not a replacement for SUMO. It exists to keep the API, frontend and
    controller tests runnable everywhere while still modelling one-hop traffic
    transfer and downstream spillback pressure.

    Every queued road user is tracked individually, so the engine can report
    exact per-vehicle delay percentiles, person-weighted delay (a bus carries
    far more people than a car), and pedestrian waiting time -- not just an
    average queue length that hides a starved approach.
    """

    EXTERNAL_APPROACHES = {
        'J1': ('north', 'west'),
        'J2': ('north', 'east'),
        'J3': ('south', 'west'),
        'J4': ('south', 'east'),
    }

    STRAIGHT_TRANSFERS = {
        ('J1', 'west'): ('J2', 'west'),
        ('J1', 'north'): ('J3', 'north'),
        ('J2', 'west'): None,
        ('J2', 'north'): ('J4', 'north'),
        ('J3', 'west'): ('J4', 'west'),
        ('J3', 'south'): ('J1', 'south'),
        ('J4', 'west'): None,
        ('J4', 'south'): ('J2', 'south'),
        ('J1', 'east'): None,
        ('J1', 'south'): None,
        ('J2', 'east'): ('J1', 'east'),
        ('J2', 'south'): None,
        ('J3', 'east'): None,
        ('J3', 'north'): None,
        ('J4', 'east'): ('J3', 'east'),
        ('J4', 'north'): None,
    }

    INITIAL_QUEUES = {
        'J1': {'north': 12, 'south': 3, 'east': 4, 'west': 22},
        'J2': {'north': 7, 'south': 4, 'east': 13, 'west': 8},
        'J3': {'north': 3, 'south': 9, 'east': 4, 'west': 14},
        'J4': {'north': 6, 'south': 10, 'east': 12, 'west': 5},
    }

    JUNCTION_IDS = ('J1', 'J2', 'J3', 'J4')

    def __init__(self):
        self.rng = random.Random(7)
        self.reset()

    # ------------------------------------------------------------------ setup

    def reset(self, scenario: str = 'normal', seed: int = 7) -> NetworkSnapshot:
        self.rng.seed(seed)
        self.tick = 0
        self.throughput = 0
        self.total_wait = 0
        self.incident: str | None = None
        self.emergency_ticks = 0
        self.arrival_multiplier = 1.0 if scenario == 'normal' else 1.8
        self.weather = 'clear'
        self.bus_share = 0.08
        self.pedestrian_rate = 1.0

        #: Per-approach demand scaling, overwritten by calibration against
        #: observed turning counts.
        self.demand_scale: dict[tuple[str, str], float] = {}

        self.lanes: dict[tuple[str, str], deque] = {}
        for jid in self.JUNCTION_IDS:
            for direction in DIRECTIONS:
                initial = self.INITIAL_QUEUES[jid][direction]
                self.lanes[(jid, direction)] = deque(
                    Vehicle(arrival_tick=0, kind=self._spawn_kind()) for _ in range(initial)
                )

        self.pedestrians: dict[str, deque] = {jid: deque() for jid in self.JUNCTION_IDS}
        self.ped_last_served: dict[str, int] = {jid: 0 for jid in self.JUNCTION_IDS}
        self.phases: dict[str, Phase] = {jid: 'NS' for jid in self.JUNCTION_IDS}
        self.modes: dict[str, str] = {jid: 'adaptive' for jid in self.JUNCTION_IDS}

        self.faults: dict[str, dict] = {}
        self.frozen_readings: dict[tuple[str, str], int] = {}
        self.emergency_run: EmergencyRun | None = None

        self.vehicle_waits: list[int] = []
        self.person_waits: list[tuple[int, float]] = []
        self.pedestrian_waits: list[int] = []
        self.approach_max_wait: dict[tuple[str, str], int] = {key: 0 for key in self.lanes}
        self.served_vehicles = 0
        self.served_people = 0.0
        self.bus_waits: list[int] = []
        self.blocked_arrivals = 0
        self.spillback_blocked = 0
        #: Offered demand per approach, counted whether or not it could
        #: physically enter. This is the quantity a traffic count measures.
        self.arrivals_seen: dict[tuple[str, str], int] = {key: 0 for key in self.lanes}
        self._committed: dict[tuple[str, str], int] = {}
        return self.snapshot()

    def _spawn_kind(self) -> str:
        return 'bus' if self.rng.random() < getattr(self, 'bus_share', 0.08) else 'car'

    # ------------------------------------------------------------- disturbance

    def inject(self, event: str) -> None:
        if event == 'rush-hour':
            self.arrival_multiplier = 2.2
            self.incident = 'rush-hour'
        elif event == 'accident':
            self.incident = 'accident:J2-west'
        elif event == 'emergency':
            self.emergency_ticks = 24
            self.incident = 'emergency-corridor:J1-J2-J4'
            self.dispatch_emergency(['J1', 'J2', 'J4'], 'ambulance')
        elif event == 'match-day':
            # Stadium egress: a sustained directional surge plus heavy footfall.
            self.arrival_multiplier = 1.6
            self.pedestrian_rate = 4.0
            self.incident = 'event:stadium-egress'
        elif event.startswith('weather:'):
            self.set_weather(event.split(':', 1)[1])
        elif event == 'clear':
            self.incident = None
            self.arrival_multiplier = 1.0
            self.emergency_ticks = 0
            self.pedestrian_rate = 1.0
            self.weather = 'clear'
            self.faults.clear()
            self.frozen_readings.clear()
            self.emergency_run = None

    def set_weather(self, condition: str) -> None:
        if condition in WEATHER_CAPACITY:
            self.weather = condition

    def inject_fault(self, kind: str, junction: str, direction: str | None = None) -> dict:
        """Simulate infrastructure failure so fallback behaviour is observable.

        ``detector-dropout``  the controller sees an empty approach
        ``detector-stuck``    the reading freezes at its current value
        ``comms-loss``        the junction stops accepting commanded phases
        ``signal-fault``      the head fails safe to all-red flashing
        """
        fault_id = f'{kind}:{junction}' + (f':{direction}' if direction else '')
        if kind == 'detector-stuck' and direction:
            self.frozen_readings[(junction, direction)] = len(self.lanes[(junction, direction)])
        self.faults[fault_id] = {
            'id': fault_id,
            'kind': kind,
            'junction': junction,
            'direction': direction,
            'since_tick': self.tick,
        }
        return self.faults[fault_id]

    def clear_faults(self) -> None:
        self.faults.clear()
        self.frozen_readings.clear()

    def dispatch_emergency(self, route: list[str], vehicle_type: str = 'ambulance') -> EmergencyRun:
        directions = self._route_directions(route)
        self.emergency_run = EmergencyRun(
            vehicle_type=vehicle_type,
            route=list(route),
            directions=directions,
            start_tick=self.tick,
            travel_remaining=0,
        )
        return self.emergency_run

    def _route_directions(self, route: list[str]) -> list[str]:
        """Approach the priority vehicle occupies at each junction on its route."""
        directions: list[str] = []
        for idx, jid in enumerate(route):
            if idx + 1 < len(route):
                nxt = route[idx + 1]
                match = next(
                    (d for d in DIRECTIONS
                     if (self.STRAIGHT_TRANSFERS.get((jid, d)) or (None,))[0] == nxt),
                    None,
                )
                directions.append(match or 'north')
            else:
                directions.append(directions[-1] if directions else 'north')
        return directions

    # ------------------------------------------------------------------ demand

    def _arrivals(self, jid: str, direction: str) -> int:
        scale = self.demand_scale.get((jid, direction), 1.0)
        return max(0, int(round(self.rng.randint(0, 3) * self.arrival_multiplier * scale)))

    def _capacity(self, junction_id: str, direction: str) -> int:
        if self.incident == 'accident:J2-west' and junction_id == 'J2' and direction == 'west':
            return 1
        return max(1, int(round(BASE_CAPACITY * WEATHER_CAPACITY.get(self.weather, 1.0))))

    # Retained so older call sites keep working.
    def _service(self, junction_id: str, direction: str) -> int:
        return self._capacity(junction_id, direction)

    # -------------------------------------------------------------- observation

    def _observed_queue(self, jid: str, direction: str) -> int:
        """What the controller sees -- degraded by any active detector fault."""
        true_length = len(self.lanes[(jid, direction)])
        for fault in self.faults.values():
            if fault['junction'] != jid or fault['direction'] != direction:
                continue
            if fault['kind'] == 'detector-dropout':
                return 0
            if fault['kind'] == 'detector-stuck':
                return self.frozen_readings.get((jid, direction), true_length)
        return true_length

    def _junction_mode(self, jid: str) -> str:
        kinds = {f['kind'] for f in self.faults.values() if f['junction'] == jid}
        if 'signal-fault' in kinds:
            return 'all-red-flash'
        if 'comms-loss' in kinds:
            return 'local-fallback'
        if any(k.startswith('detector') for k in kinds):
            return 'detector-degraded'
        return 'adaptive'

    # -------------------------------------------------------------------- step

    def step(self, phases: dict[str, Phase]) -> NetworkSnapshot:
        self.tick += 1
        self._committed = {}

        for jid, approaches in self.EXTERNAL_APPROACHES.items():
            for direction in approaches:
                lane = self.lanes[(jid, direction)]
                for _ in range(self._arrivals(jid, direction)):
                    self.arrivals_seen[(jid, direction)] += 1
                    if len(lane) >= LINK_STORAGE:
                        # The approach is physically full. The demand does not
                        # vanish -- it queues back off-network, so it is counted
                        # rather than silently dropped.
                        self.blocked_arrivals += 1
                        continue
                    lane.append(Vehicle(arrival_tick=self.tick, kind=self._spawn_kind()))

        for jid in self.JUNCTION_IDS:
            for _ in range(int(round(self.rng.randint(0, 2) * self.pedestrian_rate))):
                self.pedestrians[jid].append(self.tick)

        transfers: list[tuple[str, str, Vehicle]] = []
        exited = 0

        for jid in self.JUNCTION_IDS:
            mode = self._junction_mode(jid)
            self.modes[jid] = mode

            if mode == 'all-red-flash':
                # Fail-safe: the head flashes amber/red and serves nobody.
                self.phases[jid] = 'PED'
                continue
            if mode == 'local-fallback':
                # Comms are down; the cabinet reverts to its own fixed clock.
                commanded: Phase = 'NS' if (self.tick // 8) % 2 == 0 else 'EW'
            else:
                commanded = phases.get(jid, self.phases[jid])

            self.phases[jid] = commanded

            if commanded == 'PED':
                self._serve_pedestrians(jid)
                continue

            served_dirs = ('north', 'south') if commanded == 'NS' else ('east', 'west')
            for direction in served_dirs:
                for vehicle in self._discharge(jid, direction):
                    target = self.STRAIGHT_TRANSFERS.get((jid, direction))
                    if target is None:
                        exited += 1
                    else:
                        transfers.append((target[0], target[1], vehicle))

        for jid, direction, vehicle in transfers:
            self.lanes[(jid, direction)].append(vehicle)

        self._advance_emergency()

        self.throughput += exited
        self.total_wait += sum(len(q) for q in self.lanes.values())

        for key, lane in self.lanes.items():
            if lane:
                head_wait = self.tick - lane[0].arrival_tick
                if head_wait > self.approach_max_wait[key]:
                    self.approach_max_wait[key] = head_wait

        if self.emergency_ticks > 0:
            self.emergency_ticks -= 1
            if self.emergency_ticks == 0 and self.incident and self.incident.startswith('emergency'):
                self.incident = None

        return self.snapshot()

    def _downstream_space(self, jid: str, direction: str) -> int:
        """Room left on the link this movement discharges into.

        Movements that leave the network are never blocked. Everything else is
        limited by physical storage on the receiving approach, counting what
        other movements have already committed to it this tick.
        """
        target = self.STRAIGHT_TRANSFERS.get((jid, direction))
        if target is None:
            return LINK_STORAGE
        return LINK_STORAGE - len(self.lanes[target]) - self._committed.get(target, 0)

    def _discharge(self, jid: str, direction: str) -> list[Vehicle]:
        """Release vehicles from one approach within this tick's green capacity."""
        lane = self.lanes[(jid, direction)]
        budget = self._capacity(jid, direction)
        target = self.STRAIGHT_TRANSFERS.get((jid, direction))
        released: list[Vehicle] = []
        while lane and budget > 0:
            if self._downstream_space(jid, direction) <= 0:
                # Spillback: the receiving link is full, so this movement is
                # physically blocked no matter what the signal says.
                self.spillback_blocked += 1
                break
            head = lane[0]
            cost = BUS_SERVICE_COST if head.kind == 'bus' else 1
            if cost > budget:
                break
            lane.popleft()
            if target is not None:
                self._committed[target] = self._committed.get(target, 0) + 1
            budget -= cost
            wait = self.tick - head.arrival_tick
            self.vehicle_waits.append(wait)
            self.person_waits.append((wait, head.occupancy))
            if head.kind == 'bus':
                self.bus_waits.append(wait)
            self.served_vehicles += 1
            self.served_people += head.occupancy
            released.append(head)
        return released

    def _serve_pedestrians(self, jid: str) -> None:
        crossing = self.pedestrians[jid]
        while crossing:
            arrived = crossing.popleft()
            self.pedestrian_waits.append(self.tick - arrived)
        self.ped_last_served[jid] = self.tick

    def _advance_emergency(self) -> None:
        run = self.emergency_run
        if run is None or run.finish_tick is not None:
            return

        if run.travel_remaining > 0:
            run.travel_remaining -= 1
            run.waiting = False
            return

        jid, approach = run.at_junction, run.approach
        if jid is None or approach is None:
            run.finish_tick = self.tick
            return

        required: Phase = 'NS' if approach in ('north', 'south') else 'EW'
        if self.phases.get(jid) == required and self.modes.get(jid) != 'all-red-flash':
            run.waiting = False
            run.index += 1
            if run.index >= len(run.route):
                run.finish_tick = self.tick
            else:
                run.travel_remaining = LINK_TRAVEL_TICKS
        else:
            run.waiting = True
            run.delay_ticks += 1

    # ---------------------------------------------------------------- snapshot

    def snapshot(self) -> NetworkSnapshot:
        junctions = []
        for jid in self.JUNCTION_IDS:
            observed = {d: self._observed_queue(jid, d) for d in DIRECTIONS}
            buses = {
                d: sum(1 for v in self.lanes[(jid, d)] if v.kind == 'bus')
                for d in DIRECTIONS
            }
            mode = self._junction_mode(jid)
            junctions.append(JunctionState(
                id=jid,
                north=observed['north'],
                south=observed['south'],
                east=observed['east'],
                west=observed['west'],
                phase=self.phases[jid],
                pedestrian=len(self.pedestrians[jid]),
                ped_wait=self.tick - self.ped_last_served[jid],
                buses=buses,
                mode=mode,
                healthy=mode == 'adaptive',
            ))

        return NetworkSnapshot(
            tick=self.tick,
            junctions=junctions,
            throughput=self.throughput,
            total_wait=self.total_wait,
            incident=self.incident,
            weather=self.weather,
            faults=list(self.faults.values()),
            emergency=self.emergency_run.to_dict() if self.emergency_run else None,
            metrics=self.wait_metrics(),
        )

    # ----------------------------------------------------------------- metrics

    @staticmethod
    def _percentile(values, pct: float) -> float:
        if not values:
            return 0.0
        ordered = sorted(values)
        idx = min(len(ordered) - 1, max(0, int(round((pct / 100.0) * (len(ordered) - 1)))))
        return float(ordered[idx])

    def wait_metrics(self) -> dict:
        """Delay distribution, not just the mean.

        Averages hide starvation: an approach can sit at red for minutes while
        the network mean looks healthy. p95 and worst-case make that visible,
        and person-weighted delay stops a bus carrying 35 people from counting
        the same as one car.
        """
        waits = self.vehicle_waits
        person_delay = (
            sum(w * o for w, o in self.person_waits) / max(1e-9, sum(o for _, o in self.person_waits))
            if self.person_waits else 0.0
        )
        worst_key = max(self.approach_max_wait, key=self.approach_max_wait.get, default=None)
        return {
            'served_vehicles': self.served_vehicles,
            'served_people': round(self.served_people, 1),
            # Totals feed the fuel / CO2 / rupee conversion in services.impact.
            'total_vehicle_wait_ticks': sum(waits),
            'total_bus_wait_ticks': sum(self.bus_waits),
            'total_person_wait_ticks': round(sum(w * o for w, o in self.person_waits), 1),
            'total_pedestrian_wait_ticks': sum(self.pedestrian_waits),
            'mean_vehicle_delay': round(mean(waits), 2) if waits else 0.0,
            'p50_vehicle_delay': self._percentile(waits, 50),
            'p95_vehicle_delay': self._percentile(waits, 95),
            'max_vehicle_delay': float(max(waits)) if waits else 0.0,
            'mean_person_delay': round(person_delay, 2),
            'mean_bus_delay': round(mean(self.bus_waits), 2) if self.bus_waits else 0.0,
            'mean_pedestrian_delay': round(mean(self.pedestrian_waits), 2) if self.pedestrian_waits else 0.0,
            'p95_pedestrian_delay': self._percentile(self.pedestrian_waits, 95),
            'max_pedestrian_delay': float(max(self.pedestrian_waits)) if self.pedestrian_waits else 0.0,
            'pedestrians_served': len(self.pedestrian_waits),
            'worst_approach': f'{worst_key[0]}-{worst_key[1]}' if worst_key else None,
            'worst_approach_wait': float(self.approach_max_wait.get(worst_key, 0)) if worst_key else 0.0,
            'emergency_delay_ticks': self.emergency_run.delay_ticks if self.emergency_run else 0,
            'weather': self.weather,
            'active_faults': len(self.faults),
            # Demand that could not physically enter, and greens wasted on a
            # movement whose downstream link was already full.
            'blocked_arrivals': self.blocked_arrivals,
            'spillback_blocked_movements': self.spillback_blocked,
            'link_storage': LINK_STORAGE,
        }
