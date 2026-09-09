"""One place that knows how to run a single scenario end to end.

Benchmarks, the what-if console, the emergency demo and the impact endpoint all
need the same thing: set up the engine, apply the conditions, drive it with a
controller, and report what happened. Keeping that in one function means every
surface of the project reports comparable numbers.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict

from app.controllers.registry import DEFAULT_CONTROLLER, build
from app.controllers.safety import SafetyShield
from app.services.impact import estimate_impact
from app.simulation.mock_engine import MockTrafficEngine


@dataclass
class ScenarioConfig:
    """Everything that can be varied about a run."""

    controller: str = DEFAULT_CONTROLLER
    steps: int = 180
    seed: int = 7
    scenario: str = 'normal'
    event: str | None = None
    event_tick: int = 30
    weather: str = 'clear'
    demand_multiplier: float = 1.0
    pedestrian_rate: float = 1.0
    bus_share: float = 0.08
    faults: list[dict] = field(default_factory=list)
    fault_tick: int = 40
    shielded: bool = True
    emergency_route: list[str] | None = None
    emergency_tick: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def simulate(config: ScenarioConfig) -> dict:
    """Run one scenario and return metrics, impact and the audit trail."""
    engine = MockTrafficEngine()
    engine.reset(
        scenario='rush' if config.scenario.startswith('rush') else 'normal',
        seed=config.seed,
    )
    engine.arrival_multiplier *= max(0.1, config.demand_multiplier)
    engine.pedestrian_rate = max(0.0, config.pedestrian_rate)
    engine.bus_share = min(1.0, max(0.0, config.bus_share))
    engine.set_weather(config.weather)

    controller = build(config.controller, shielded=config.shielded)
    steps = max(1, min(config.steps, 2000))

    peak_queue = 0
    phase_switches = 0
    previous: dict | None = None

    for tick in range(steps):
        if config.event and tick == config.event_tick:
            engine.inject(config.event)
        if config.faults and tick == config.fault_tick:
            for fault in config.faults:
                engine.inject_fault(
                    fault.get('kind', 'detector-dropout'),
                    fault.get('junction', 'J1'),
                    fault.get('direction'),
                )
        if config.emergency_route and tick == (config.emergency_tick or 0):
            engine.dispatch_emergency(config.emergency_route, 'ambulance')

        snapshot = engine.snapshot()
        actions = controller.choose_phases(snapshot)
        if previous is not None:
            phase_switches += sum(actions[jid] != previous.get(jid) for jid in actions)
        previous = dict(actions)
        engine.step(actions)
        peak_queue = max(peak_queue, sum(len(q) for q in engine.lanes.values()))

    final = engine.snapshot()
    metrics = final.metrics
    emergency = engine.emergency_run

    result = {
        'controller': config.controller,
        'shielded': config.shielded,
        'steps': steps,
        'seed': config.seed,
        'scenario': config.scenario,
        'event': config.event,
        'weather': config.weather,
        'throughput': final.throughput,
        'average_network_queue': round(final.total_wait / max(1, steps), 3),
        'final_queue': sum(j.queue for j in final.junctions),
        'peak_queue': peak_queue,
        'phase_switches': phase_switches,
        'metrics': metrics,
        'impact': estimate_impact(metrics, steps),
    }

    if emergency is not None:
        travel = (
            (emergency.finish_tick - emergency.start_tick)
            if emergency.finish_tick is not None else None
        )
        result['emergency'] = {
            **emergency.to_dict(),
            'travel_ticks': travel,
            'travel_seconds': round(travel * 5.0, 1) if travel is not None else None,
            'completed': emergency.finish_tick is not None,
        }

    if isinstance(controller, SafetyShield):
        result['safety'] = controller.override_summary()
        result['decisions_tail'] = controller.recent_decisions(limit=20)

    return result
