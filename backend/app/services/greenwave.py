"""Corridor offset coordination and the time-space diagram that proves it.

Getting each junction locally right is not enough: if neighbouring signals turn
green at the wrong moment relative to each other, a platoon stops at every one.
Coordination sets an *offset* per junction so the platoon meets a green at each
stop -- the classic green wave.

The time-space diagram is the standard way traffic engineers read this. Time on
one axis, distance along the corridor on the other, green windows drawn as bars
and vehicle trajectories as diagonal lines. A working green wave is immediately
visible as a clear diagonal channel through the bars.
"""

from __future__ import annotations

#: Default free-flow progression speed along a coordinated corridor.
DEFAULT_SPEED_KMPH = 40.0

#: Seconds of real time represented by one simulation tick.
TICK_SECONDS = 5.0

#: Resolution used when measuring how wide the through band is, in ticks.
BAND_RESOLUTION = 0.05


def _link_positions(corridor: list[str], travel_ticks: list[float], speed_kmph: float) -> list[float]:
    """Cumulative distance of each junction from the start of the corridor."""
    metres_per_tick = speed_kmph * 1000.0 / 3600.0 * TICK_SECONDS
    positions = [0.0]
    for ticks in travel_ticks:
        positions.append(positions[-1] + ticks * metres_per_tick)
    return positions


def _cumulative(travel_ticks: list[float]) -> list[float]:
    out = [0.0]
    for t in travel_ticks:
        out.append(out[-1] + t)
    return out


def _band_width(offsets: list[float], arrivals: list[float], cycle: float, green: float) -> float:
    """Width of the departure window that clears every downstream junction."""
    width = 0.0
    steps = int(green / BAND_RESOLUTION)
    for i in range(steps):
        depart = i * BAND_RESOLUTION
        if all(
            ((depart + arrivals[k] - offsets[k]) % cycle) < green
            for k in range(len(offsets))
        ):
            width += BAND_RESOLUTION
    return round(width, 3)


def plan_green_wave(
    corridor: list[str],
    cycle: float = 16.0,
    green: float = 8.0,
    travel_ticks: list[float] | None = None,
    speed_kmph: float = DEFAULT_SPEED_KMPH,
    cycles_to_plot: int = 4,
) -> dict:
    """Compute progression offsets and everything needed to draw the diagram."""
    if len(corridor) < 2:
        raise ValueError('a corridor needs at least two junctions')
    if travel_ticks is None:
        travel_ticks = [4.0] * (len(corridor) - 1)
    if len(travel_ticks) != len(corridor) - 1:
        raise ValueError('travel_ticks must contain len(corridor)-1 values')
    green = min(green, cycle)

    arrivals = _cumulative(travel_ticks)
    positions = _link_positions(corridor, travel_ticks, speed_kmph)

    # A platoon released at the start of green at the first junction should meet
    # the start of green everywhere downstream, so the offset simply tracks its
    # travel time, folded back into one cycle.
    offsets = [round(a % cycle, 3) for a in arrivals]
    uncoordinated = [0.0] * len(corridor)

    junctions = []
    for idx, jid in enumerate(corridor):
        windows = []
        for c in range(cycles_to_plot):
            start = offsets[idx] + c * cycle
            windows.append([round(start, 3), round(start + green, 3)])
        junctions.append({
            'id': jid,
            'position_m': round(positions[idx], 1),
            'offset_ticks': offsets[idx],
            'offset_seconds': round(offsets[idx] * TICK_SECONDS, 1),
            'green_windows': windows,
        })

    coordinated_band = _band_width(offsets, arrivals, cycle, green)
    uncoordinated_band = _band_width(uncoordinated, arrivals, cycle, green)

    trajectories = []
    for c in range(cycles_to_plot):
        launch = offsets[0] + c * cycle
        trajectories.append([
            {'t': round(launch + arrivals[i], 3), 'x': round(positions[i], 1)}
            for i in range(len(corridor))
        ])

    return {
        'corridor': corridor,
        'cycle_ticks': cycle,
        'green_ticks': green,
        'cycle_seconds': round(cycle * TICK_SECONDS, 1),
        'speed_kmph': speed_kmph,
        'travel_ticks': travel_ticks,
        'junctions': junctions,
        'trajectories': trajectories,
        'band': {
            'coordinated_ticks': coordinated_band,
            'uncoordinated_ticks': uncoordinated_band,
            'coordinated_seconds': round(coordinated_band * TICK_SECONDS, 1),
            'efficiency_pct': round(100.0 * coordinated_band / max(1e-9, green), 1),
            'uncoordinated_efficiency_pct': round(100.0 * uncoordinated_band / max(1e-9, green), 1),
            'stops_avoided_per_platoon': len(corridor) - 1 if coordinated_band > 0 else 0,
        },
        'note': (
            'Band width is the slice of the first green during which a vehicle can '
            'depart and still clear every downstream junction without stopping.'
        ),
    }
