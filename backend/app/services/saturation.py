"""Lane-less discharge: how fast a *mixed* queue actually clears.

Signal-control theory is built on lane discipline. Vehicles are assumed to
queue single file and cross the stop line one per lane per saturation headway,
and a static PCU factor converts other classes into car equivalents. Both
assumptions come from road environments that Indian urban traffic does not
resemble.

In lane-less flow two-wheelers filter forward into lateral gaps and discharge
two or three abreast inside one nominal lane. What limits the number of
vehicles crossing the stop line per second is therefore the *lateral* road
space each class occupies, not a space-equivalence factor calibrated for
moving flow.

So discharge time per vehicle of class ``i`` on an approach ``W`` lane-widths
wide is modelled directly:

    t_i = w_i * h_i / W

    w_i   lateral width occupied, in lane-equivalents
    h_i   saturation headway in its own track, in seconds

The model is deliberately calibrated to reproduce the conventional result
where the conventional assumptions hold: a car at ``w=1.0, h=2.0`` on a
two-lane approach gives ``t=1.0 s``, which is 1800 veh/h/lane -- the textbook
saturation flow. It departs from convention only as lane discipline breaks
down, which is exactly the regime of interest.

Why this matters for control
----------------------------
Every controller in this project -- and in most of the literature -- measures
pressure in *vehicles*. A queue of 30 two-wheelers and a queue of 30 cars look
identical to it, while the first clears in about a third of the time. Measuring
pressure in **discharge-seconds** instead is what ``heterogeneous-pressure``
does, and it is the one thing here that is not standard practice.

Every number below is an assumption. ``docs/HETEROGENEOUS_FLOW.md`` records
where each comes from and what would be needed to calibrate it against a real
junction. No performance claim should be made from these defaults alone.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Lane-widths on a modelled approach.
DEFAULT_LANES = 2.0


@dataclass(frozen=True)
class VehicleClass:
    """Physical and demand characteristics of one road-user class."""

    name: str
    #: Lateral road space occupied, in lane-equivalents. The whole model turns
    #: on this: a two-wheeler needs well under a lane, so several discharge
    #: side by side where one car would fit.
    width: float
    #: Saturation headway within its own track, seconds.
    headway: float
    #: Conventional static PCU, as a PCU-based controller would apply it.
    static_pcu: float
    #: Average people carried, for person-delay metrics.
    occupancy: float
    #: Queue storage consumed, in car-lengths.
    storage: float


#: Defaults are centre estimates for an Indian urban arterial.
VEHICLE_CLASSES: dict[str, VehicleClass] = {
    'two-wheeler': VehicleClass('two-wheeler', 0.40, 1.6, 0.50, 1.2, 0.35),
    'auto':        VehicleClass('auto',        0.60, 2.2, 0.80, 2.5, 0.55),
    'car':         VehicleClass('car',         1.00, 2.0, 1.00, 1.5, 1.00),
    'bus':         VehicleClass('bus',         1.00, 3.6, 3.00, 35.0, 2.60),
}

#: Composition of an Indian urban arterial stream. Two-wheeler dominance is the
#: single most important difference from the traffic these algorithms were
#: designed for.
DEFAULT_MIX = {'two-wheeler': 0.45, 'car': 0.33, 'auto': 0.18, 'bus': 0.04}

#: A lane-disciplined, car-dominated stream, for contrast.
WESTERN_MIX = {'car': 0.88, 'bus': 0.06, 'two-wheeler': 0.04, 'auto': 0.02}


def discharge_seconds(kind: str, lanes: float = DEFAULT_LANES) -> float:
    """Green time one vehicle of this class consumes at the stop line."""
    v = VEHICLE_CLASSES[kind]
    return v.width * v.headway / lanes


def implied_pcu(kind: str, lanes: float = DEFAULT_LANES) -> float:
    """PCU implied by discharge, i.e. what the static factor ought to be."""
    return discharge_seconds(kind, lanes) / discharge_seconds('car', lanes)


def queue_discharge_seconds(counts: dict[str, int], lanes: float = DEFAULT_LANES) -> float:
    """Green time a mixed queue needs to clear. This is the true pressure."""
    return sum(n * discharge_seconds(k, lanes) for k, n in counts.items())


def queue_pcu(counts: dict[str, int]) -> float:
    """What a static-PCU controller believes the same queue is worth."""
    return sum(n * VEHICLE_CLASSES[k].static_pcu for k, n in counts.items())


def queue_storage(counts: dict[str, int]) -> float:
    """Physical room the queue occupies, in car-lengths."""
    return sum(n * VEHICLE_CLASSES[k].storage for k, n in counts.items())


def pcu_error(counts: dict[str, int], lanes: float = DEFAULT_LANES) -> dict:
    """How far a static-PCU green allocation drifts from the real requirement.

    Positive error means the PCU controller over-allocates green: it holds the
    approach green after the queue has already cleared, and that time is taken
    from somebody else.
    """
    actual = queue_discharge_seconds(counts, lanes)
    # One PCU per second over two lanes is the textbook saturation flow, so the
    # PCU belief is expressed in the same units for comparison.
    believed = queue_pcu(counts) * discharge_seconds('car', lanes)
    total = sum(counts.values())
    return {
        'vehicles': total,
        'composition': {k: round(n / max(1, total), 3) for k, n in counts.items()},
        'actual_green_seconds': round(actual, 2),
        'pcu_green_seconds': round(believed, 2),
        'error_seconds': round(believed - actual, 2),
        'error_pct': round(100.0 * (believed - actual) / max(1e-9, actual), 1),
    }


def sample_composition(rng, mix: dict[str, float] | None = None) -> str:
    """Draw one vehicle class from a stream composition."""
    mix = mix or DEFAULT_MIX
    roll = rng.random()
    cumulative = 0.0
    for kind, share in mix.items():
        cumulative += share
        if roll < cumulative:
            return kind
    return 'car'


def comparison_report(lanes: float = DEFAULT_LANES) -> dict:
    """The evidence that a composition-aware controller is worth building.

    Reproduces the study that justified this work, so a reviewer can re-run it
    rather than take the claim on trust.
    """
    classes = [
        {
            'class': kind,
            'static_pcu': v.static_pcu,
            'implied_pcu': round(implied_pcu(kind, lanes), 3),
            'discharge_seconds': round(discharge_seconds(kind, lanes), 3),
            'overstatement_pct': round(
                100.0 * (v.static_pcu - implied_pcu(kind, lanes))
                / max(1e-9, implied_pcu(kind, lanes)), 1),
        }
        for kind, v in VEHICLE_CLASSES.items()
    ]

    curve = []
    for share in (0.0, 0.15, 0.30, 0.45, 0.60, 0.75):
        total = 30
        tw = round(total * share)
        bus = round(total * 0.04)
        auto = round(total * 0.14)
        counts = {
            'two-wheeler': tw, 'auto': auto, 'bus': bus,
            'car': max(0, total - tw - bus - auto),
        }
        row = pcu_error(counts, lanes)
        row['two_wheeler_share'] = share
        curve.append(row)

    return {
        'lanes': lanes,
        'classes': classes,
        'error_vs_two_wheeler_share': curve,
        'reading': (
            'Positive error means a static-PCU controller holds an approach green '
            'after its queue has cleared. The error grows with two-wheeler share, '
            'which is precisely the regime Indian urban arterials operate in.'
        ),
        'caveat': (
            'Physical parameters are centre estimates, not measurements. They must '
            'be calibrated against a real junction before any performance claim.'
        ),
    }
