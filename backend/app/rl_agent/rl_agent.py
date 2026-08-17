import torch

from .dqn import DQNAgent
from .ppo import PPOAgent

class RLAgent:
    """
    Main Reinforcement Learning Agent
    """

    def __init__(
        self,
        algorithm="dqn",
        state_dim=4,
        action_dim=2,
    ):
        self.algorithm = algorithm.lower()

        if self.algorithm == "dqn":
            self.agent = DQNAgent(
                state_dim=state_dim,
                action_dim=action_dim,
            )

        elif self.algorithm == "ppo":
            self.agent = PPOAgent(
                state_dim=state_dim,
                action_dim=action_dim,
            )

        else:
            raise ValueError(
                f"Unknown algorithm: {algorithm}"
            )

    def act(self, state):
        return self.agent.act(state)

    def remember(self, *args):
        if hasattr(self.agent, "remember"):
            self.agent.remember(*args)

    def update(self):
        if hasattr(self.agent, "update"):
            self.agent.update()

    def predict(self, state):
        return self.act(state)

    def save(self, path):
        if hasattr(self.agent, "model"):
            torch.save(
                self.agent.model.state_dict(),
                path,
            )
        elif hasattr(self.agent, "actor"):
            torch.save(
                self.agent.actor.state_dict(),
                path,
            )

    def load(self, path):
        if hasattr(self.agent, "model"):
            self.agent.model.load_state_dict(
                torch.load(path)
            )

        elif hasattr(self.agent, "actor"):
            self.agent.actor.load_state_dict(
                torch.load(path)
            )


if __name__ == "__main__":

    state = [0.5, 0.2, 0.1, 0.9]

    agent = RLAgent(
        algorithm="dqn",
        state_dim=4,
        action_dim=2,
    )

    action = agent.predict(state)

    print("Selected Action:", action)