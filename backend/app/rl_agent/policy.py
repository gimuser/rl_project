import random
import torch


class EpsilonGreedyPolicy:
    """
    Epsilon-Greedy Policy for action selection.
    """

    def __init__(
        self,
        epsilon=1.0,
        epsilon_min=0.01,
        epsilon_decay=0.995,
    ):
        self.epsilon = epsilon
        self.epsilon_min = epsilon_min
        self.epsilon_decay = epsilon_decay

    def select_action(self, q_values):
        """
        Select an action using epsilon-greedy strategy.
        """

        if random.random() < self.epsilon:
            return random.randint(0, len(q_values) - 1)

        return torch.argmax(q_values).item()

    def decay(self):
        """
        Reduce exploration over time.
        """

        if self.epsilon > self.epsilon_min:
            self.epsilon *= self.epsilon_decay