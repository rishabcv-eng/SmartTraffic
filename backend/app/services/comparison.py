from __future__ import annotations

from app.controllers.registry import CONTROLLERS, DEFAULT_CONTROLLER, build
from app.simulation.mock_engine import MockTrafficEngine


def run_comparison(left: str = 'fixed-time', right: str = DEFAULT_CONTROLLER, steps: int = 90, seed: int = 7, event: str | None = 'accident', event_tick: int = 20, scenario: str = 'normal', shielded: bool = True) -> dict:
    """Return aligned frame sequences and end metrics from identical demand."""
    steps = max(1, min(steps, 300))
    event_tick = max(0, min(event_tick, steps - 1))
    names = (left, right)
    engines = [MockTrafficEngine(), MockTrafficEngine()]
    controllers = [build(name, shielded=shielded) for name in names]
    for engine in engines:
        engine.reset(scenario='rush' if scenario == 'rush' else 'normal', seed=seed)

    histories = [[], []]
    peaks = [0, 0]
    for tick in range(steps + 1):
        for i, engine in enumerate(engines):
            snap = engine.snapshot()
            histories[i].append(snap.to_dict())
            peaks[i] = max(peaks[i], sum(j.queue for j in snap.junctions))
        if tick == steps:
            break
        if event and tick == event_tick:
            for engine in engines:
                engine.inject(event)
        for engine, controller in zip(engines, controllers):
            snap = engine.snapshot()
            engine.step(controller.choose_phases(snap))

    def metrics(engine, peak):
        final = engine.snapshot()
        detail = final.metrics
        return {
            'throughput': final.throughput,
            'average_network_queue': round(final.total_wait / max(1, steps), 3),
            'final_queue': sum(j.queue for j in final.junctions),
            'peak_queue': peak,
            'mean_vehicle_delay': detail['mean_vehicle_delay'],
            'p95_vehicle_delay': detail['p95_vehicle_delay'],
            'worst_approach_wait': detail['worst_approach_wait'],
            'mean_person_delay': detail['mean_person_delay'],
            'mean_pedestrian_delay': detail['mean_pedestrian_delay'],
        }

    return {
        'seed': seed,
        'steps': steps,
        'scenario': scenario,
        'event': event,
        'event_tick': event_tick,
        'shielded': shielded,
        'left': {'controller': names[0], 'frames': histories[0], 'metrics': metrics(engines[0], peaks[0])},
        'right': {'controller': names[1], 'frames': histories[1], 'metrics': metrics(engines[1], peaks[1])},
    }
