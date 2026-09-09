"""Hardware-in-the-loop bridge: drive real signal heads from the simulation.

A screen full of charts is easy to disbelieve. A physical model junction whose
LEDs change because the controller decided they should is not. This module
translates the abstract phase of each junction into the three aspects a real
signal head shows, including the amber clearance the simulation implies but
does not represent as a separate tick.

The wire format is a single ASCII line so an ESP32 or Arduino can parse it with
``strtok`` and no JSON library:

    T42|J1:GRR|J2:RGR|J3:RRA|J4:GRR

Aspect codes are ``G`` green, ``A`` amber, ``R`` red, in the order
NS, EW, pedestrian. See ``hardware/README.md`` for the wiring.
"""

from __future__ import annotations

ASPECTS = {'green': 'G', 'amber': 'A', 'red': 'R'}


class SignalHeadBridge:
    """Convert phase decisions into signal-head aspects with amber clearance."""

    def __init__(self, amber_ticks: int = 1):
        self.amber_ticks = amber_ticks
        self.previous: dict[str, str] = {}
        self.amber_remaining: dict[str, int] = {}
        self.losing: dict[str, str] = {}

    def _aspects(self, junction) -> dict[str, str]:
        jid, phase = junction.id, junction.phase

        if junction.mode == 'all-red-flash':
            # Fail-safe state: everything red, which on real hardware is driven
            # as a flashing amber/red rather than a dark head.
            return {'ns': 'red', 'ew': 'red', 'ped': 'red', 'fault': True}

        previous = self.previous.get(jid)
        if previous is not None and previous != phase:
            self.amber_remaining[jid] = self.amber_ticks
            self.losing[jid] = previous
        self.previous[jid] = phase

        remaining = self.amber_remaining.get(jid, 0)
        if remaining > 0:
            self.amber_remaining[jid] = remaining - 1
            losing = self.losing.get(jid)
            return {
                'ns': 'amber' if losing == 'NS' else 'red',
                'ew': 'amber' if losing == 'EW' else 'red',
                'ped': 'red',
                'fault': False,
            }

        return {
            'ns': 'green' if phase == 'NS' else 'red',
            'ew': 'green' if phase == 'EW' else 'red',
            'ped': 'green' if phase == 'PED' else 'red',
            'fault': False,
        }

    def render(self, snapshot) -> dict:
        """Aspect state for every junction, plus the compact wire line."""
        heads = []
        for junction in snapshot.junctions:
            aspects = self._aspects(junction)
            heads.append({
                'id': junction.id,
                'phase': junction.phase,
                'mode': junction.mode,
                'ns': aspects['ns'],
                'ew': aspects['ew'],
                'ped': aspects['ped'],
                'fault': aspects['fault'],
                'code': ''.join(ASPECTS[aspects[k]] for k in ('ns', 'ew', 'ped')),
                'queue': junction.queue,
                'pedestrians': junction.pedestrian,
            })

        wire = f'T{snapshot.tick}|' + '|'.join(f'{h["id"]}:{h["code"]}' for h in heads)
        return {
            'tick': snapshot.tick,
            'heads': heads,
            'wire': wire,
            'legend': {'G': 'green', 'A': 'amber', 'R': 'red', 'order': 'NS,EW,PED'},
            'poll_interval_ms': 500,
        }
