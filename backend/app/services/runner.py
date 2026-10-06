from __future__ import annotations

import asyncio
import copy
import os
from dataclasses import dataclass

from app.controllers.registry import CONTROLLERS, DEFAULT_CONTROLLER, build
from app.controllers.safety import SafetyShield
from app.services.hil import SignalHeadBridge
from app.services.impact import estimate_impact
from app.simulation.mock_engine import MockTrafficEngine
from app.simulation.sumo_engine import SumoTrafficEngine


@dataclass
class RunConfig:
    controller: str = DEFAULT_CONTROLLER
    scenario: str = 'normal'
    seed: int = 7
    #: The live control room always runs shielded; this is the deployable
    #: configuration and the one the audit trail describes.
    shielded: bool = True


def make_engine():
    mode = os.getenv('SMARTTRAFFIC_ENGINE', 'mock').lower()
    if mode == 'sumo':
        return SumoTrafficEngine(gui=os.getenv('SMARTTRAFFIC_SUMO_GUI', '0') == '1')
    return MockTrafficEngine()


class SimulationRunner:
    def __init__(self):
        self.engine = make_engine()
        self.config = RunConfig()
        self.controller = build(self.config.controller, shielded=self.config.shielded)
        self.running = False
        self.clients: set = set()
        self.bridge = SignalHeadBridge()

    # ------------------------------------------------------------------ setup

    def reset(self, config: RunConfig | None = None):
        if config:
            self.config = config
        self.controller = build(self.config.controller, shielded=self.config.shielded)
        self.bridge = SignalHeadBridge()
        return self.engine.reset(self.config.scenario, self.config.seed)

    def snapshot(self):
        if hasattr(self.engine, 'snapshot'):
            snap = self.engine.snapshot()
        else:
            snap = self.engine._snapshot()
        if isinstance(self.controller, SafetyShield):
            snap.decisions = self.controller.decisions
        return snap

    # ------------------------------------------------------------ disturbance

    def inject(self, event: str):
        self.engine.inject(event)
        return self.snapshot()

    def inject_fault(self, kind: str, junction: str, direction: str | None = None):
        if not isinstance(self.engine, MockTrafficEngine):
            raise RuntimeError('fault injection is only available on the mock engine')
        self.engine.inject_fault(kind, junction, direction)
        return self.snapshot()

    def clear_faults(self):
        if isinstance(self.engine, MockTrafficEngine):
            self.engine.clear_faults()
        return self.snapshot()

    def set_weather(self, condition: str):
        if isinstance(self.engine, MockTrafficEngine):
            self.engine.set_weather(condition)
        return self.snapshot()

    def dispatch_emergency(self, route: list[str], vehicle_type: str = 'ambulance'):
        if not isinstance(self.engine, MockTrafficEngine):
            raise RuntimeError('emergency dispatch is only available on the mock engine')
        self.engine.dispatch_emergency(route, vehicle_type)
        return self.snapshot()

    # -------------------------------------------------------------- execution

    def one_step(self):
        current = self.snapshot()
        snap = self.engine.step(self.controller.choose_phases(current))
        if isinstance(self.controller, SafetyShield):
            snap.decisions = self.controller.decisions
        return snap

    def forecast(self, horizon: int = 15):
        if not isinstance(self.engine, MockTrafficEngine):
            return self.snapshot()
        engine = copy.deepcopy(self.engine)
        controller = copy.deepcopy(self.controller)
        for _ in range(max(1, min(horizon, 120))):
            snap = engine.snapshot()
            engine.step(controller.choose_phases(snap))
        return engine.snapshot()

    # ---------------------------------------------------------------- reports

    def safety_report(self, limit: int = 60, junction: str | None = None) -> dict:
        if not isinstance(self.controller, SafetyShield):
            return {
                'shielded': False,
                'note': 'The active controller is running without the safety shield.',
            }
        return {
            'shielded': True,
            'controller': self.controller.name,
            'constraints': {
                'min_green': self.controller.min_green,
                'max_green': self.controller.max_green,
                'max_pedestrian_wait': self.controller.max_pedestrian_wait,
            },
            'summary': self.controller.override_summary(),
            'decisions': self.controller.recent_decisions(limit=limit, junction=junction),
        }

    def live_impact(self) -> dict:
        snap = self.snapshot()
        return estimate_impact(snap.metrics, max(1, snap.tick))

    def hil_state(self) -> dict:
        return self.bridge.render(self.snapshot())

    # ------------------------------------------------------------------- loop

    async def loop(self):
        self.running = True
        try:
            while self.running:
                snap = self.one_step().to_dict()
                dead = []
                for ws in list(self.clients):
                    try:
                        await ws.send_json(snap)
                    except Exception:
                        dead.append(ws)
                for ws in dead:
                    self.clients.discard(ws)
                await asyncio.sleep(0.6)
        finally:
            self.running = False
