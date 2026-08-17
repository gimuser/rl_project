import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim

from .networks import ActorNetwork, CriticNetwork


class PPOAgent:
    """
    Proximal Policy Optimization (PPO) Agent.

    This implementation uses an Actor-Critic architecture.
    """

    def __init__(
        self,
        state_dim,
        action_dim,
        lr=3e-4,
        gamma=0.99,
        eps_clip=0.2,
        k_epochs=4,
    ):
        self.gamma = gamma
        self.eps_clip = eps_clip
        self.k_epochs = k_epochs

        self.actor = ActorNetwork(state_dim, action_dim)
        self.critic = CriticNetwork(state_dim)

        self.optimizer = optim.Adam(
            list(self.actor.parameters()) +
            list(self.critic.parameters()),
            lr=lr,
        )

        self.states = []
        self.actions = []
        self.log_probs = []
        self.rewards = []
        self.dones = []

    def act(self, state):
        """
        Select an action using the current policy.

        Args:
            state: Environment state.

        Returns:
            tuple:
                (action, log_probability)
        """

        if not isinstance(state, torch.Tensor):
            state = torch.FloatTensor(state)

        if state.dim() == 1:
            state = state.unsqueeze(0)

        with torch.no_grad():
            probs = self.actor(state)

        probs = torch.clamp(probs, 1e-8, 1.0)
        probs = probs / probs.sum(dim=-1, keepdim=True)

        distribution = torch.distributions.Categorical(probs)

        action = distribution.sample()

        log_prob = distribution.log_prob(action)

        return action.item(), log_prob

    def remember(
        self,
        state,
        action,
        log_prob,
        reward,
        done,
    ):
        """
        Store one transition.
        """

        self.states.append(np.asarray(state, dtype=np.float32))
        self.actions.append(action)
        self.log_probs.append(log_prob.detach())
        self.rewards.append(float(reward))
        self.dones.append(done)

    def compute_returns(self):
        """
        Compute discounted returns.
        """

        returns = []
        discounted_reward = 0.0

        for reward, done in zip(
            reversed(self.rewards),
            reversed(self.dones),
        ):

            if done:
                discounted_reward = 0.0

            discounted_reward = (
                reward +
                self.gamma * discounted_reward
            )

            returns.insert(0, discounted_reward)

        return torch.tensor(
            returns,
            dtype=torch.float32,
        )

    def compute_advantages(
        self,
        returns,
        values,
    ):
        """
        Compute normalized advantages.
        """

        advantages = returns - values.detach()

        if len(advantages) > 1:

            std = advantages.std(unbiased=False)

            if std > 1e-8:
                advantages = (
                    advantages - advantages.mean()
                ) / (std + 1e-8)

        return advantages

    def update(self):
        """
        Update Actor and Critic networks.
        """

        if len(self.states) < 2:
            print("Not enough samples for PPO update.")
            return

        states = torch.tensor(
            np.array(self.states),
            dtype=torch.float32,
        )

        actions = torch.tensor(
            self.actions,
            dtype=torch.long,
        )

        old_log_probs = torch.stack(
            self.log_probs
        ).detach()

        returns = self.compute_returns()

        for _ in range(self.k_epochs):

            values = self.critic(states).squeeze(-1)

            advantages = self.compute_advantages(
                returns,
                values,
            )

            probs = self.actor(states)

            probs = torch.clamp(
                probs,
                min=1e-8,
                max=1.0,
            )

            probs = probs / probs.sum(
                dim=-1,
                keepdim=True,
            )

            distribution = torch.distributions.Categorical(
                probs
            )

            new_log_probs = distribution.log_prob(
                actions
            )

            entropy = distribution.entropy().mean()

            ratios = torch.exp(
                new_log_probs - old_log_probs
            )

            surr1 = ratios * advantages

            surr2 = torch.clamp(
                ratios,
                1 - self.eps_clip,
                1 + self.eps_clip,
            ) * advantages

            actor_loss = -torch.min(
                surr1,
                surr2,
            ).mean()

            critic_loss = nn.functional.mse_loss(
                values,
                returns,
            )

            loss = (
                actor_loss
                + 0.5 * critic_loss
                - 0.01 * entropy
            )

            self.optimizer.zero_grad()
            loss.backward()
            self.optimizer.step()

        self.states.clear()
        self.actions.clear()
        self.log_probs.clear()
        self.rewards.clear()
        self.dones.clear()

        print("PPO Update Completed.")
