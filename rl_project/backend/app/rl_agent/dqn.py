from __future__ import annotations

import random
from typing import Optional

import numpy as np
import torch
from torch import nn


class DoubleDQN:

    def __init__(
        self,
        input_dim: int,
        n_actions: int,
        learning_rate: float = 1e-3,
        gamma: float = 0.95,
        hidden_dim: int = 128,
        device: Optional[str] = None,
    ):

        self.device = torch.device(
            device or ("cuda" if torch.cuda.is_available() else "cpu")
        )

        self.gamma = gamma
        self.n_actions = n_actions

        self.online = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, n_actions),
        ).to(self.device)

        self.target = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, n_actions),
        ).to(self.device)

        self.target.load_state_dict(self.online.state_dict())

        self.optimizer = torch.optim.Adam(
            self.online.parameters(),
            lr=learning_rate,
        )

        self.loss_fn = nn.SmoothL1Loss()

    @torch.no_grad()
    def q_values(self, states: np.ndarray) -> np.ndarray:

        x = torch.as_tensor(
            states,
            dtype=torch.float32,
            device=self.device,
        )

        return self.online(x).cpu().numpy()

    @torch.no_grad()
    def act(self, states: np.ndarray) -> np.ndarray:

        q = self.q_values(states)

        return np.argmax(q, axis=1)

    def update_counterfactual(
        self,
        states,
        reward_matrix,
        next_states,
        dones,
    ):
        """
        Offline counterfactual Bellman update.

        reward_matrix[:, action] contains the real reward for every
        valid action for each state.
        """
        states = torch.as_tensor(
            states,
            dtype=torch.float32,
            device=self.device,
        )

        reward_matrix = torch.as_tensor(
            reward_matrix,
            dtype=torch.float32,
            device=self.device,
        )

        next_states = torch.as_tensor(
            next_states,
            dtype=torch.float32,
            device=self.device,
        )

        dones = torch.as_tensor(
            dones,
            dtype=torch.float32,
            device=self.device,
        )

        q = self.online(states)

        with torch.no_grad():
            next_online = self.online(next_states)
            next_actions = next_online.argmax(
                dim=1,
                keepdim=True,
            )

            next_target = self.target(next_states)

            next_q = next_target.gather(
                1,
                next_actions,
            ).squeeze(1)

            bootstrap = (
                (1.0 - dones) * self.gamma * next_q
            )

            targets = (
                reward_matrix
                + bootstrap.unsqueeze(1)
            )

        loss = self.loss_fn(
            q,
            targets,
        )

        self.optimizer.zero_grad()
        loss.backward()

        torch.nn.utils.clip_grad_norm_(
            self.online.parameters(),
            5.0,
        )

        self.optimizer.step()

        return float(loss.item())

    def update(
        self,
        states,
        actions,
        rewards,
        next_states,
        dones,
    ):

        states = torch.as_tensor(
            states,
            dtype=torch.float32,
            device=self.device,
        )

        actions = torch.as_tensor(
            actions,
            dtype=torch.long,
            device=self.device,
        )

        rewards = torch.as_tensor(
            rewards,
            dtype=torch.float32,
            device=self.device,
        )

        next_states = torch.as_tensor(
            next_states,
            dtype=torch.float32,
            device=self.device,
        )

        dones = torch.as_tensor(
            dones,
            dtype=torch.float32,
            device=self.device,
        )

        q = self.online(states)

        q_selected = q.gather(
            1,
            actions.unsqueeze(1),
        ).squeeze(1)

        with torch.no_grad():

            next_online = self.online(next_states)

            next_actions = next_online.argmax(
                dim=1,
                keepdim=True,
            )

            next_target = self.target(next_states)

            next_q = next_target.gather(
                1,
                next_actions,
            ).squeeze(1)

            target = rewards + (
                1.0 - dones
            ) * self.gamma * next_q

        loss = self.loss_fn(
            q_selected,
            target,
        )

        self.optimizer.zero_grad()
        loss.backward()

        torch.nn.utils.clip_grad_norm_(
            self.online.parameters(),
            5.0,
        )

        self.optimizer.step()

        return float(loss.item())

    def update_target(self):

        self.target.load_state_dict(
            self.online.state_dict()
        )

    def save(self, path: str):

        torch.save(
            {
                "online": self.online.state_dict(),
                "target": self.target.state_dict(),
                "gamma": self.gamma,
                "n_actions": self.n_actions,
            },
            path,
        )

    def load(self, path: str):

        checkpoint = torch.load(
            path,
            map_location=self.device,
            weights_only=False,
        )

        self.online.load_state_dict(
            checkpoint["online"]
        )

        self.target.load_state_dict(
            checkpoint.get(
                "target",
                checkpoint["online"],
            )
        )


# ==========================================================================
# BACKWARD-COMPATIBLE DQNAgent API
# ==========================================================================
#
# Existing FastAPI/application code imports:
#
#     from app.rl_agent.dqn import DQNAgent
#
# The accepted DoubleDQN remains the authoritative implementation.
# This facade only adapts the older application API to DoubleDQN.
# ==========================================================================

class DQNAgent:
    """
    Application compatibility facade over the accepted DoubleDQN model.
    """

    def __init__(
        self,
        state_dim: int,
        action_dim: int,
        gamma: float = 0.95,
        lr: float = 3e-4,
        **kwargs,
    ):
        self.state_dim = int(state_dim)
        self.action_dim = int(action_dim)
        self.gamma = float(gamma)
        self.lr = float(lr)

        self._agent = DoubleDQN(
            input_dim=self.state_dim,
            n_actions=self.action_dim,
            learning_rate=self.lr,
            gamma=self.gamma,
            hidden_dim=int(
                kwargs.get("hidden_dim", 128)
            ),
        )

        # Application code may access .model.
        self.model = self._agent.online

        self.target_model = self._agent.target

    def act(
        self,
        state,
        evaluate: bool = True,
    ):
        """
        Return one action for a single state or a batch.

        Application compatibility:
            single state -> int
            batch         -> numpy array
        """

        import numpy as np

        x = np.asarray(
            state,
            dtype=np.float32,
        )

        if x.ndim == 1:
            return int(
                self._agent.act(
                    x.reshape(1, -1)
                )[0]
            )

        return self._agent.act(x)

    def predict(self, state):
        return self.act(
            state,
            evaluate=True,
        )

    def q_values(self, states):
        return self._agent.q_values(states)

    def update(
        self,
        states,
        actions,
        rewards,
        next_states,
        dones,
    ):
        return self._agent.update(
            states,
            actions,
            rewards,
            next_states,
            dones,
        )

    def update_target(self):
        return self._agent.update_target()

    def save(self, path):
        return self._agent.save(path)

    def load(self, path):
        result = self._agent.load(path)
        self.model = self._agent.online
        self.target_model = self._agent.target
        return result


