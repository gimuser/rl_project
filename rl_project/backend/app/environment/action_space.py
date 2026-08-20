"""Canonical action space for the SOAR RL agent."""

from dataclasses import dataclass
import random


CLOSE_ALERT = 0
ESCALATE = 1
REQUEST_HUMAN_VALIDATION = 2

ACTION_NAMES = {
    CLOSE_ALERT: "allow",
    ESCALATE: "block",
    REQUEST_HUMAN_VALIDATION: "human_review",
}


@dataclass(frozen=True)
class ActionSpace:
    n: int = 3

    def sample(self):
        return random.randrange(self.n)

    def contains(self, action: int) -> bool:
        return (
            isinstance(action, int)
            and 0 <= action < self.n
        )

    def name(self, action: int) -> str:
        if not self.contains(action):
            raise ValueError(
                f"Invalid action: {action}"
            )
        return ACTION_NAMES[action]


ACTION_SPACE = ActionSpace()
