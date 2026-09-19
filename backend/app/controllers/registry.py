"""Single source of truth for the available controllers."""

from __future__ import annotations

from app.controllers.actuated import ActuatedController
from app.controllers.base import Controller
from app.controllers.coordinated_pressure import CoordinatedPressureController
from app.controllers.fixed_time import FixedTimeController
from app.controllers.gated_pressure import GatedPressureController
from app.controllers.heterogeneous_pressure import (
    HeterogeneousPressureController,
    HeterogeneousTimedController,
    PCUPressureController,
    PCUTimedController,
    PersonSecondsController,
)
from app.controllers.max_pressure import MaxPressureController
from app.controllers.mpc_lite import MPCLiteController
from app.controllers.network_max_pressure import NetworkMaxPressureController
from app.controllers.predictive_pressure import PredictivePressureController
from app.controllers.rl_controller import RLController
from app.controllers.safety import SafetyShield
from app.controllers.transit_priority import TransitPriorityController

CONTROLLERS: dict[str, type[Controller]] = {
    'fixed-time': FixedTimeController,
    'actuated': ActuatedController,
    'max-pressure': MaxPressureController,
    'network-max-pressure': NetworkMaxPressureController,
    'predictive-pressure-v2': PredictivePressureController,
    'mpc-lite-v1': MPCLiteController,
    'transit-priority-v1': TransitPriorityController,
    'gated-pressure-v1': GatedPressureController,
    'coordinated-pressure-v1': CoordinatedPressureController,
    'pcu-pressure-v1': PCUPressureController,
    'heterogeneous-pressure-v1': HeterogeneousPressureController,
    'pcu-timed-v1': PCUTimedController,
    'heterogeneous-timed-v1': HeterogeneousTimedController,
    'person-seconds-v1': PersonSecondsController,
    'rl-network-v2': RLController,
}

#: Controllers that must never be run without the safety shield in front.
SHIELD_REQUIRED = {'rl-network-v2'}

DEFAULT_CONTROLLER = 'coordinated-pressure-v1'


def build(name: str, shielded: bool = False, **shield_kwargs) -> Controller:
    """Instantiate a controller by name, optionally behind the safety shield."""
    controller = CONTROLLERS.get(name, CONTROLLERS[DEFAULT_CONTROLLER])()
    if shielded or name in SHIELD_REQUIRED:
        return SafetyShield(controller, **shield_kwargs)
    return controller


def describe() -> list[dict]:
    return [
        {
            'name': name,
            'class': cls.__name__,
            'shield_required': name in SHIELD_REQUIRED,
            'summary': (cls.__doc__ or '').strip().split('\n')[0],
        }
        for name, cls in CONTROLLERS.items()
    ]
