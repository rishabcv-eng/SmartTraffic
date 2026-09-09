from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Literal

Phase = Literal['NS', 'EW', 'PED']

DIRECTIONS = ('north', 'south', 'east', 'west')

#: Average vehicle occupancy by class, used for person-delay metrics.
#: Sources are Indian urban travel surveys; tune per city during calibration.
OCCUPANCY = {
    'car': 1.5,
    'two-wheeler': 1.2,
    'bus': 35.0,
    'ambulance': 2.0,
}


@dataclass
class JunctionState:
    id: str
    north: int
    south: int
    east: int
    west: int
    phase: Phase = 'NS'
    pedestrian: int = 0
    ped_wait: int = 0
    buses: dict[str, int] = field(default_factory=lambda: {d: 0 for d in DIRECTIONS})
    mode: str = 'adaptive'
    healthy: bool = True

    @property
    def queue(self) -> int:
        return self.north + self.south + self.east + self.west

    @property
    def pressure_ns(self) -> int:
        return self.north + self.south

    @property
    def pressure_ew(self) -> int:
        return self.east + self.west

    def person_pressure(self, phase: Phase) -> float:
        """Queue pressure weighted by how many *people* are waiting, not cars."""
        directions = ('north', 'south') if phase == 'NS' else ('east', 'west')
        total = 0.0
        for direction in directions:
            buses = self.buses.get(direction, 0)
            cars = max(0, getattr(self, direction) - buses)
            total += cars * OCCUPANCY['car'] + buses * OCCUPANCY['bus']
        return total

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload['queue'] = self.queue
        payload['person_queue'] = round(
            self.person_pressure('NS') + self.person_pressure('EW'), 1
        )
        return payload


@dataclass
class NetworkSnapshot:
    tick: int
    junctions: list[JunctionState]
    throughput: int = 0
    total_wait: int = 0
    incident: str | None = None
    weather: str = 'clear'
    faults: list[dict] = field(default_factory=list)
    emergency: dict | None = None
    decisions: list[dict] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        total_queue = sum(j.queue for j in self.junctions)
        return {
            'tick': self.tick,
            'junctions': [j.to_dict() for j in self.junctions],
            'throughput': self.throughput,
            'total_wait': self.total_wait,
            'total_queue': total_queue,
            'incident': self.incident,
            'weather': self.weather,
            'faults': self.faults,
            'emergency': self.emergency,
            'decisions': self.decisions,
            'metrics': self.metrics,
            'pedestrians_waiting': sum(j.pedestrian for j in self.junctions),
            'degraded': any(not j.healthy for j in self.junctions),
        }
