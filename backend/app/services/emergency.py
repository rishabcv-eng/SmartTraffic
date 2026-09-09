from __future__ import annotations

from dataclasses import dataclass


PRIORITY_PROFILES = {
    'ambulance': {'priority': 100, 'lead_seconds': 12.0, 'hold_seconds': 20.0, 'max_delay_seconds': 0.0},
    'fire': {'priority': 95, 'lead_seconds': 14.0, 'hold_seconds': 22.0, 'max_delay_seconds': 0.0},
    'disaster-response': {'priority': 90, 'lead_seconds': 12.0, 'hold_seconds': 20.0, 'max_delay_seconds': 2.0},
    'police': {'priority': 80, 'lead_seconds': 10.0, 'hold_seconds': 16.0, 'max_delay_seconds': 3.0},
    'vip': {'priority': 55, 'lead_seconds': 8.0, 'hold_seconds': 12.0, 'max_delay_seconds': 8.0},
}


@dataclass(frozen=True)
class CorridorStep:
    junction_id: str
    eta_seconds: float
    green_lead_seconds: float
    hold_seconds: float
    release_seconds: float

    def to_dict(self) -> dict:
        return {
            'junction_id': self.junction_id,
            'eta_seconds': round(self.eta_seconds, 1),
            'green_lead_seconds': round(self.green_lead_seconds, 1),
            'hold_seconds': round(self.hold_seconds, 1),
            'release_seconds': round(self.release_seconds, 1),
        }


def plan_green_corridor(
    route: list[str],
    segment_travel_seconds: list[float] | None = None,
    lead_seconds: float | None = None,
    hold_seconds: float | None = None,
    vehicle_type: str = 'ambulance',
) -> dict:
    profile = PRIORITY_PROFILES.get(vehicle_type, PRIORITY_PROFILES['ambulance'])
    lead = float(profile['lead_seconds'] if lead_seconds is None else lead_seconds)
    hold = float(profile['hold_seconds'] if hold_seconds is None else hold_seconds)

    if not route:
        return {
            'vehicle_type': vehicle_type,
            'priority': profile['priority'],
            'route': [],
            'schedule': [],
            'total_eta_seconds': 0.0,
            'strategy': 'rolling-green-wave',
        }

    if segment_travel_seconds is None:
        segment_travel_seconds = [35.0] * max(0, len(route) - 1)
    if len(segment_travel_seconds) != max(0, len(route) - 1):
        raise ValueError('segment_travel_seconds must contain len(route)-1 values')

    eta = 0.0
    schedule: list[CorridorStep] = []
    for idx, junction_id in enumerate(route):
        release = max(0.0, eta - lead) + hold
        schedule.append(CorridorStep(junction_id, eta, lead, hold, release))
        if idx < len(segment_travel_seconds):
            eta += max(1.0, float(segment_travel_seconds[idx]))

    return {
        'vehicle_type': vehicle_type,
        'priority': profile['priority'],
        'route': route,
        'schedule': [step.to_dict() for step in schedule],
        'total_eta_seconds': round(eta, 1),
        'max_delay_seconds': profile['max_delay_seconds'],
        'strategy': 'rolling-green-wave',
        'recovery': 'restore-network-optimum-after-passage',
    }


def run_preemption_comparison(
    route: list[str] | None = None,
    baseline: str = 'fixed-time',
    candidate: str = 'predictive-pressure-v2',
    steps: int = 140,
    seed: int = 7,
    dispatch_tick: int = 20,
    scenario: str = 'rush',
) -> dict:
    """Send the same ambulance through the same traffic under both controllers.

    The baseline runs unshielded, so the ambulance takes whatever green it
    happens to meet. The candidate runs behind the safety shield, which holds a
    rolling green corridor ahead of the vehicle. The difference in door-to-door
    travel time is the headline number.
    """
    from app.services.scenario import ScenarioConfig, simulate

    route = route or ['J1', 'J2', 'J4']

    def run(controller: str, shielded: bool, dispatch: bool = True) -> dict:
        return simulate(ScenarioConfig(
            controller=controller,
            steps=steps,
            seed=seed,
            scenario=scenario,
            shielded=shielded,
            emergency_route=route if dispatch else None,
            emergency_tick=dispatch_tick if dispatch else None,
        ))

    without = run(baseline, shielded=False)
    with_preemption = run(candidate, shielded=True)
    # Same controller, same seed, no ambulance: isolates what preemption itself
    # cost the network from what simply differs between the two controllers.
    undisturbed = run(candidate, shielded=True, dispatch=False)

    a = without.get('emergency', {})
    b = with_preemption.get('emergency', {})
    saved = None
    if a.get('travel_ticks') is not None and b.get('travel_ticks') is not None:
        saved = a['travel_ticks'] - b['travel_ticks']

    def cost(run_result: dict) -> dict:
        """What the rest of the network paid for the priority passage."""
        return {
            'average_network_queue': run_result['average_network_queue'],
            'mean_vehicle_delay': run_result['metrics']['mean_vehicle_delay'],
            'throughput': run_result['throughput'],
        }

    return {
        'route': route,
        'seed': seed,
        'scenario': scenario,
        'dispatch_tick': dispatch_tick,
        'without_preemption': {
            'controller': baseline,
            'emergency': a,
            'network': cost(without),
        },
        'with_preemption': {
            'controller': f'{candidate}+shield',
            'emergency': b,
            'network': cost(with_preemption),
        },
        'cost_of_priority': {
            'controller': f'{candidate}+shield',
            'network_without_ambulance': cost(undisturbed),
            'network_with_ambulance': cost(with_preemption),
            'extra_mean_vehicle_delay': round(
                with_preemption['metrics']['mean_vehicle_delay']
                - undisturbed['metrics']['mean_vehicle_delay'], 2
            ),
            'throughput_given_up': undisturbed['throughput'] - with_preemption['throughput'],
        },
        'saved_ticks': saved,
        'saved_seconds': round(saved * 5.0, 1) if saved is not None else None,
        'improvement_pct': (
            round(100.0 * saved / max(1e-9, a['travel_ticks']), 1)
            if saved is not None and a.get('travel_ticks') else None
        ),
        'red_light_waits_avoided': (
            a.get('delay_ticks', 0) - b.get('delay_ticks', 0)
        ),
        'note': (
            'Priority is not free: compare the network columns to see the delay '
            'the rest of the traffic absorbed while the corridor was held.'
        ),
    }
