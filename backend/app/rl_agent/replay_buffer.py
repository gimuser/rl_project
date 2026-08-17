from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass

import numpy as np


@dataclass
class Transition:
    state: np.ndarray
    action: int
    reward: float
    next_state: np.ndarray
    done: bool


class ReplayBuffer:

    def __init__(self, capacity: int = 200_000):
        self.buffer = deque(maxlen=capacity)

    def push(
        self,
        state,
        action,
        reward,
        next_state,
        done,
    ):
        self.buffer.append(
            Transition(
                np.asarray(state, dtype=np.float32),
                int(action),
                float(reward),
                np.asarray(next_state, dtype=np.float32),
                bool(done),
            )
        )

    def sample(self, batch_size: int):

        batch = random.sample(self.buffer, batch_size)

        states = np.stack([x.state for x in batch])
        actions = np.asarray([x.action for x in batch], dtype=np.int64)
        rewards = np.asarray([x.reward for x in batch], dtype=np.float32)
        next_states = np.stack([x.next_state for x in batch])
        dones = np.asarray([x.done for x in batch], dtype=np.float32)

        return states, actions, rewards, next_states, dones

    def __len__(self):
        return len(self.buffer)
