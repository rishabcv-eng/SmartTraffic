"""Reinforcement-learning signal control with a safety shield in front of it.

The usual objection to RL for traffic signals is that a learned policy has no
guarantees: it can starve an approach, flicker, or do something unexplainable
at 2am. The answer used here is *shielded* RL -- the learned policy only ever
*proposes* a phase, and ``controllers.safety.SafetyShield`` enforces minimum
green, starvation limits, pedestrian waiting limits and fault fallback on top
of it. The policy can be wrong without the junction becoming unsafe.

**Why this learns the network phase rather than each junction's.**

The first version ran an independent agent per junction. It was the worst
controller in the benchmark by a wide margin -- around 39% worse than a plain
fixed clock at normal demand. The cause was structural, not a tuning problem:
independent agents each maximise their own local discharge, which is precisely
what destroys the phase alignment that lets a platoon clear several junctions
without stopping. The same effect is why every locally-greedy controller here
loses to a fixed clock, and why ``coordinated-pressure-v1`` wins.

So the agent now chooses one phase for the whole network, which is the same
action space the coordinated controller searches. That also shrinks the state
space enough to learn it properly in under a second.

**Why the reward is not queue length.** Rewarding low queues teaches the policy
to refuse traffic: an approach held at red stops accepting arrivals once it
fills, so the network looks emptier while serving fewer people. The reward is
vehicles actually discharged, minus the demand turned away at the boundary,
which cannot be gamed that way.
"""

from __future__ import annotations

import random
from functools import lru_cache

from app.controllers.base import Controller
from app.models import NetworkSnapshot, Phase

ACTIONS: tuple[Phase, Phase] = ('NS', 'EW')

#: Network-wide pressure buckets. Coarse on purpose: a compact state space
#: learns fast and generalises, and the shield handles fine-grained safety.
BUCKET_EDGES = (20, 45, 80, 130, 200)


def bucket(value: float) -> int:
    for idx, edge in enumerate(BUCKET_EDGES):
        if value < edge:
            return idx
    return len(BUCKET_EDGES)


def encode(pressure_ns: float, pressure_ew: float, phase: Phase) -> tuple:
    """Network state: total NS pressure, total EW pressure, current phase."""
    return (bucket(pressure_ns), bucket(pressure_ew), 0 if phase == 'NS' else 1)


def network_pressures(snapshot: NetworkSnapshot) -> tuple[float, float]:
    ns = sum(j.pressure_ns for j in snapshot.junctions)
    ew = sum(j.pressure_ew for j in snapshot.junctions)
    return float(ns), float(ew)


@lru_cache(maxsize=1)
def train_policy(
    episodes: int = 120,
    steps: int = 140,
    alpha: float = 0.2,
    gamma: float = 0.92,
    seed: int = 17,
) -> dict:
    """Learn a discharge-maximising network policy on the mock engine.

    Cached and fixed-seeded, so every benchmark run sees the identical policy
    and results stay reproducible.
    """
    from app.simulation.mock_engine import MockTrafficEngine

    rng = random.Random(seed)
    q: dict[tuple, list[float]] = {}
    engine = MockTrafficEngine()

    def values(state: tuple) -> list[float]:
        return q.setdefault(state, [0.0, 0.0])

    for episode in range(episodes):
        engine.reset(scenario='rush' if episode % 2 else 'normal', seed=seed + episode)
        snapshot = engine.snapshot()
        state = encode(*network_pressures(snapshot), snapshot.junctions[0].phase)
        # Explore hard early, then settle onto the learned policy.
        epsilon = max(0.05, 0.45 * (1.0 - episode / max(1, episodes)))

        for _ in range(steps):
            if rng.random() < epsilon:
                idx = rng.randrange(len(ACTIONS))
            else:
                vals = values(state)
                idx = 0 if vals[0] >= vals[1] else 1
            action = ACTIONS[idx]

            served_before = engine.served_vehicles
            blocked_before = engine.blocked_arrivals
            nxt = engine.step({j.id: action for j in snapshot.junctions})

            discharged = engine.served_vehicles - served_before
            turned_away = engine.blocked_arrivals - blocked_before
            switched = state[2] != idx
            # Serve traffic, do not turn it away, and do not churn the phase.
            reward = float(discharged) - 2.0 * float(turned_away) - (1.5 if switched else 0.0)

            new_state = encode(*network_pressures(nxt), action)
            best_next = max(values(new_state))
            current = values(state)
            current[idx] += alpha * (reward + gamma * best_next - current[idx])
            state = new_state
            snapshot = nxt

    return {state: list(vals) for state, vals in q.items()}


class RLController(Controller):
    """Greedy policy over the trained Q-table.

    Deploy behind ``SafetyShield``: this class provides the objective, the
    shield provides the guarantees.
    """

    name = 'rl-network-v2'
    requires_shield = True

    def __init__(self):
        self.policy = train_policy()

    def choose_phases(self, snapshot: NetworkSnapshot) -> dict[str, Phase]:
        ns, ew = network_pressures(snapshot)
        current = snapshot.junctions[0].phase if snapshot.junctions else 'NS'
        state = encode(ns, ew, current if current in ACTIONS else 'NS')
        values = self.policy.get(state)
        if values is None:
            # Unseen state: fall back to the network max-pressure rule rather
            # than to an arbitrary choice.
            phase: Phase = 'NS' if ns >= ew else 'EW'
        else:
            phase = ACTIONS[0] if values[0] >= values[1] else ACTIONS[1]
        return {j.id: phase for j in snapshot.junctions}

    def explain(self, snapshot: NetworkSnapshot) -> dict:
        """What the policy saw and what it valued, for the audit trail."""
        ns, ew = network_pressures(snapshot)
        current = snapshot.junctions[0].phase if snapshot.junctions else 'NS'
        state = encode(ns, ew, current if current in ACTIONS else 'NS')
        values = self.policy.get(state, [0.0, 0.0])
        return {
            'pressure_ns': round(ns, 1),
            'pressure_ew': round(ew, 1),
            'state': {'ns_bucket': state[0], 'ew_bucket': state[1], 'phase': current},
            'q_ns': round(values[0], 3),
            'q_ew': round(values[1], 3),
            'known_state': state in self.policy,
            'states_learned': len(self.policy),
        }
