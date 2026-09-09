"""Reinforcement-learning signal control with a safety shield in front of it.

The usual objection to RL for traffic signals is that a learned policy has no
guarantees: it can starve an approach, flicker, or do something unexplainable
at 2am. The answer used here is *shielded* RL -- the learned policy only ever
*proposes* a phase, and ``controllers.safety.SafetyShield`` enforces minimum
green, starvation limits, pedestrian waiting limits and fault fallback on top
of it. The policy can be wrong without the junction becoming unsafe.

The policy itself is deliberately small: tabular Q-learning over bucketed
queue pressure, with one table shared across junctions. That keeps it trainable
in under a second at import time, fully deterministic for reproducible
benchmarks, and inspectable -- you can print the entire policy, which is not
true of a neural controller.
"""

from __future__ import annotations

import random
from functools import lru_cache

from app.controllers.base import Controller
from app.models import NetworkSnapshot, Phase

ACTIONS: tuple[Phase, Phase] = ('NS', 'EW')

#: Queue-pressure buckets. Coarse on purpose: a compact state space learns fast
#: and generalises, and the shield handles the fine-grained safety timing.
BUCKET_EDGES = (5, 10, 20, 35)


def bucket(value: float) -> int:
    for idx, edge in enumerate(BUCKET_EDGES):
        if value < edge:
            return idx
    return len(BUCKET_EDGES)


def encode(pressure_ns: float, pressure_ew: float, phase: Phase) -> tuple:
    return (bucket(pressure_ns), bucket(pressure_ew), 0 if phase == 'NS' else 1)


@lru_cache(maxsize=1)
def train_policy(
    episodes: int = 30,
    steps: int = 100,
    alpha: float = 0.25,
    gamma: float = 0.9,
    epsilon: float = 0.15,
    seed: int = 17,
) -> dict:
    """Learn a queue-minimising policy on the mock engine.

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
        states = {
            j.id: encode(j.pressure_ns, j.pressure_ew, j.phase)
            for j in snapshot.junctions
        }

        for _ in range(steps):
            actions: dict[str, Phase] = {}
            chosen: dict[str, int] = {}
            for jid, state in states.items():
                if rng.random() < epsilon:
                    idx = rng.randrange(len(ACTIONS))
                else:
                    vals = values(state)
                    idx = 0 if vals[0] >= vals[1] else 1
                chosen[jid] = idx
                actions[jid] = ACTIONS[idx]

            nxt = engine.step(actions)
            for j in nxt.junctions:
                # Reward penalises the queue left behind, and mild switching,
                # so the policy learns to hold a phase long enough to clear it.
                switched = ACTIONS[chosen[j.id]] != (
                    'NS' if states[j.id][2] == 0 else 'EW'
                )
                reward = -float(j.queue) - (1.0 if switched else 0.0)
                new_state = encode(j.pressure_ns, j.pressure_ew, j.phase)
                best_next = max(values(new_state))
                idx = chosen[j.id]
                current = values(states[j.id])
                current[idx] += alpha * (reward + gamma * best_next - current[idx])
                states[j.id] = new_state

    return {state: list(vals) for state, vals in q.items()}


class RLController(Controller):
    """Greedy policy over the trained Q-table.

    Deploy behind ``SafetyShield``: this class provides the objective, the
    shield provides the guarantees.
    """

    name = 'rl-q-learning-v1'
    requires_shield = True

    def __init__(self):
        self.policy = train_policy()

    def choose_phases(self, snapshot: NetworkSnapshot) -> dict[str, Phase]:
        actions: dict[str, Phase] = {}
        for j in snapshot.junctions:
            state = encode(j.pressure_ns, j.pressure_ew, j.phase)
            values = self.policy.get(state)
            if values is None:
                # Unseen state: fall back to the max-pressure rule rather than
                # to an arbitrary choice.
                actions[j.id] = 'NS' if j.pressure_ns >= j.pressure_ew else 'EW'
            else:
                actions[j.id] = ACTIONS[0] if values[0] >= values[1] else ACTIONS[1]
        return actions

    def explain(self, snapshot: NetworkSnapshot) -> list[dict]:
        """Per-junction view of what the policy saw and what it valued."""
        rows = []
        for j in snapshot.junctions:
            state = encode(j.pressure_ns, j.pressure_ew, j.phase)
            values = self.policy.get(state, [0.0, 0.0])
            rows.append({
                'junction': j.id,
                'state': {'ns_bucket': state[0], 'ew_bucket': state[1], 'phase': j.phase},
                'q_ns': round(values[0], 3),
                'q_ew': round(values[1], 3),
                'known_state': state in self.policy,
            })
        return rows
