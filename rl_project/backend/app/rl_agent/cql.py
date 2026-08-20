from __future__ import annotations

import numpy as np
import torch

from .dqn import DoubleDQN


class CQLDoubleDQN(DoubleDQN):
    """Discrete conservative Q-learning over the counterfactual action matrix."""

    def __init__(self, *args, cql_alpha: float = 1.0, **kwargs):
        super().__init__(*args, **kwargs)
        self.cql_alpha = float(cql_alpha)

    def update_cql(self, states, reward_matrix, next_states, dones) -> float:
        states_t = torch.as_tensor(states, dtype=torch.float32, device=self.device)
        rewards_t = torch.as_tensor(reward_matrix, dtype=torch.float32, device=self.device)
        next_t = torch.as_tensor(next_states, dtype=torch.float32, device=self.device)
        dones_t = torch.as_tensor(dones, dtype=torch.float32, device=self.device)
        q = self.online(states_t)
        with torch.no_grad():
            next_online = self.online(next_t)
            next_actions = next_online.argmax(dim=1, keepdim=True)
            next_q = self.target(next_t).gather(1, next_actions).squeeze(1)
            targets = rewards_t + ((1.0 - dones_t) * self.gamma * next_q).unsqueeze(1)
        bellman = self.loss_fn(q, targets)
        conservative = torch.logsumexp(q, dim=1).mean() - q.mean()
        loss = bellman + self.cql_alpha * conservative
        self.optimizer.zero_grad(); loss.backward(); torch.nn.utils.clip_grad_norm_(self.online.parameters(), 5.0); self.optimizer.step()
        return float(loss.item())

    def save(self, path: str):
        torch.save({"algorithm": "cql", "online": self.online.state_dict(), "target": self.target.state_dict(), "gamma": self.gamma, "n_actions": self.n_actions, "cql_alpha": self.cql_alpha}, path)
