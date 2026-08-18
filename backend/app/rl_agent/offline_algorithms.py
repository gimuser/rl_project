"""Executable offline-RL candidates for the SOC experiment runner.

IQL and BCQ normally require logged behavior actions. The current dataset does not
contain them, so this module provides an explicit reward-derived behavior proxy.
Every artifact records that proxy mode was used; it must not be described as
historical agent behavior.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import numpy as np
import torch
from torch import nn
import torch.nn.functional as F

from .cql import CQLDoubleDQN
from .dqn import DoubleDQN


@dataclass(frozen=True)
class AlgorithmSpec:
    name: str
    display_name: str
    family: str
    requires_logged_actions: bool
    runnable_without_logged_actions: bool
    description: str


ALGORITHMS = {
    "double_dqn": AlgorithmSpec("double_dqn", "Double DQN", "value-based", False, True, "Incident-level counterfactual Double DQN baseline."),
    "cql": AlgorithmSpec("cql", "Conservative Q-Learning (CQL)", "offline-value", False, True, "Conservative value learning over the counterfactual action set."),
    "iql": AlgorithmSpec("iql", "Implicit Q-Learning (IQL)", "offline-value", True, True, "Discrete IQL using an explicit reward-derived behavior proxy when logged actions are absent."),
    "bcq": AlgorithmSpec("bcq", "Batch-Constrained Q-Learning (BCQ)", "offline-value", True, True, "Discrete BCQ using an explicit reward-derived behavior proxy when logged actions are absent."),
}


def get_algorithm(name: str) -> AlgorithmSpec:
    key = name.strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {"ddqn": "double_dqn", "doubleddqn": "double_dqn", "conservative_q_learning": "cql"}
    key = aliases.get(key, key)
    if key not in ALGORITHMS:
        raise ValueError(f"Unsupported offline-RL algorithm: {name}")
    return ALGORITHMS[key]


def behavior_actions_from_reward(reward_matrix: np.ndarray) -> np.ndarray:
    return np.argmax(reward_matrix, axis=1).astype(np.int64)


def algorithm_metadata(name: str) -> dict[str, Any]:
    spec = get_algorithm(name)
    proxy = spec.name in {"iql", "bcq"}
    return {
        "algorithm": spec.name,
        "display_name": spec.display_name,
        "family": spec.family,
        "requires_logged_actions": spec.requires_logged_actions,
        "behavior_action_mode": "reward_proxy" if proxy else "counterfactual_reward_matrix",
        "research_warning": "IQL/BCQ use reward-derived behavior actions because no historical agent-action column exists in the current dataset." if proxy else None,
    }


def _runtime_params(name: str) -> dict[str, Any]:
    """Read per-algorithm values injected by the control-room API."""
    try:
        raw = os.getenv("REAL_RL_ALGORITHM_PARAMS_JSON", "{}")
        payload = json.loads(raw)
        value = payload.get(name, {})
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


class IQLProxy(DoubleDQN):
    def __init__(self, *args, expectile: float = 0.7, beta: float = 3.0, **kwargs):
        lr = float(kwargs.get("learning_rate", 1e-3))
        super().__init__(*args, **kwargs)
        first = self.online[0]
        hidden = first.out_features if isinstance(first, nn.Linear) else 128
        input_dim = first.in_features if isinstance(first, nn.Linear) else 1
        self.value = nn.Sequential(nn.Linear(input_dim, hidden), nn.ReLU(), nn.Linear(hidden, hidden), nn.ReLU(), nn.Linear(hidden, 1)).to(self.device)
        self.policy = nn.Sequential(nn.Linear(input_dim, hidden), nn.ReLU(), nn.Linear(hidden, hidden), nn.ReLU(), nn.Linear(hidden, self.n_actions)).to(self.device)
        self.value_optimizer = torch.optim.Adam(self.value.parameters(), lr=lr)
        self.policy_optimizer = torch.optim.Adam(self.policy.parameters(), lr=lr)
        self.expectile = float(expectile)
        self.beta = float(beta)

    def update_iql(self, states, reward_matrix, next_states, dones):
        states_t = torch.as_tensor(states, dtype=torch.float32, device=self.device)
        rewards_t = torch.as_tensor(reward_matrix, dtype=torch.float32, device=self.device)
        next_t = torch.as_tensor(next_states, dtype=torch.float32, device=self.device)
        dones_t = torch.as_tensor(dones, dtype=torch.float32, device=self.device)
        behavior = torch.as_tensor(behavior_actions_from_reward(reward_matrix), dtype=torch.long, device=self.device)
        q_all = self.online(states_t)
        q_behavior = q_all.gather(1, behavior[:, None]).squeeze(1)
        v = self.value(states_t).squeeze(1)
        with torch.no_grad():
            next_v = self.value(next_t).squeeze(1)
            targets = rewards_t.gather(1, behavior[:, None]).squeeze(1) + (1.0 - dones_t) * self.gamma * next_v
        diff = q_behavior.detach() - v
        weights = torch.where(diff > 0, torch.as_tensor(self.expectile, device=self.device), torch.as_tensor(1.0 - self.expectile, device=self.device))
        value_loss = (weights * diff.square()).mean()
        self.value_optimizer.zero_grad(); value_loss.backward(); self.value_optimizer.step()
        advantage = (q_all.detach() - self.value(states_t).detach().squeeze(1)[:, None]).clamp(-8.0, 8.0)
        aw = torch.exp(self.beta * advantage).clamp(max=20.0)
        logp = F.log_softmax(self.policy(states_t), dim=1)
        policy_loss = -(aw.gather(1, behavior[:, None]).squeeze(1) * logp.gather(1, behavior[:, None]).squeeze(1)).mean()
        self.policy_optimizer.zero_grad(); policy_loss.backward(); self.policy_optimizer.step()
        q_target = rewards_t + ((1.0 - dones_t) * self.gamma * next_v).unsqueeze(1)
        q_loss = self.loss_fn(q_all, q_target)
        self.optimizer.zero_grad(); q_loss.backward(); torch.nn.utils.clip_grad_norm_(self.online.parameters(), 5.0); self.optimizer.step()
        return float((q_loss + value_loss + policy_loss).detach().item())

    @torch.no_grad()
    def act(self, states):
        return self.policy(torch.as_tensor(states, dtype=torch.float32, device=self.device)).argmax(dim=1).cpu().numpy()

    def save(self, path: str):
        torch.save({"algorithm": "iql", "online": self.online.state_dict(), "target": self.target.state_dict(), "value": self.value.state_dict(), "policy": self.policy.state_dict(), "gamma": self.gamma, "n_actions": self.n_actions, "expectile": self.expectile, "beta": self.beta}, path)

    def load(self, path: str):
        checkpoint = torch.load(path, map_location=self.device, weights_only=False)
        self.online.load_state_dict(checkpoint["online"]); self.target.load_state_dict(checkpoint.get("target", checkpoint["online"])); self.value.load_state_dict(checkpoint["value"]); self.policy.load_state_dict(checkpoint["policy"])


class BCQProxy(DoubleDQN):
    def __init__(self, *args, threshold: float = 0.05, **kwargs):
        lr = float(kwargs.get("learning_rate", 1e-3))
        super().__init__(*args, **kwargs)
        first = self.online[0]
        hidden = first.out_features if isinstance(first, nn.Linear) else 128
        input_dim = first.in_features if isinstance(first, nn.Linear) else 1
        self.behavior = nn.Sequential(nn.Linear(input_dim, hidden), nn.ReLU(), nn.Linear(hidden, hidden), nn.ReLU(), nn.Linear(hidden, self.n_actions)).to(self.device)
        self.behavior_optimizer = torch.optim.Adam(self.behavior.parameters(), lr=lr)
        self.threshold = float(threshold)

    def update_bcq(self, states, reward_matrix, next_states, dones):
        states_t = torch.as_tensor(states, dtype=torch.float32, device=self.device)
        rewards_t = torch.as_tensor(reward_matrix, dtype=torch.float32, device=self.device)
        next_t = torch.as_tensor(next_states, dtype=torch.float32, device=self.device)
        dones_t = torch.as_tensor(dones, dtype=torch.float32, device=self.device)
        behavior = torch.as_tensor(behavior_actions_from_reward(reward_matrix), dtype=torch.long, device=self.device)
        behavior_loss = F.cross_entropy(self.behavior(states_t), behavior)
        self.behavior_optimizer.zero_grad(); behavior_loss.backward(); self.behavior_optimizer.step()
        q = self.online(states_t)
        with torch.no_grad():
            probs = F.softmax(self.behavior(next_t), dim=1)
            next_q = self.target(next_t)
            mask = probs >= self.threshold * probs.max(dim=1, keepdim=True).values
            next_max = next_q.masked_fill(~mask, -1e9).max(dim=1).values
            scalar_target = rewards_t[torch.arange(len(behavior), device=self.device), behavior] + (1.0 - dones_t) * self.gamma * next_max
        q_selected = q.gather(1, behavior[:, None]).squeeze(1)
        q_loss = self.loss_fn(q_selected, scalar_target)
        self.optimizer.zero_grad(); q_loss.backward(); torch.nn.utils.clip_grad_norm_(self.online.parameters(), 5.0); self.optimizer.step()
        return float((q_loss + behavior_loss).detach().item())

    @torch.no_grad()
    def act(self, states):
        states_t = torch.as_tensor(states, dtype=torch.float32, device=self.device)
        q = self.online(states_t)
        probs = F.softmax(self.behavior(states_t), dim=1)
        mask = probs >= self.threshold * probs.max(dim=1, keepdim=True).values
        return q.masked_fill(~mask, -1e9).argmax(dim=1).cpu().numpy()

    def save(self, path: str):
        torch.save({"algorithm": "bcq", "online": self.online.state_dict(), "target": self.target.state_dict(), "behavior": self.behavior.state_dict(), "gamma": self.gamma, "n_actions": self.n_actions, "threshold": self.threshold}, path)

    def load(self, path: str):
        checkpoint = torch.load(path, map_location=self.device, weights_only=False)
        self.online.load_state_dict(checkpoint["online"]); self.target.load_state_dict(checkpoint.get("target", checkpoint["online"])); self.behavior.load_state_dict(checkpoint["behavior"])


def build_model(name: str, *, input_dim: int, n_actions: int, learning_rate: float, gamma: float, hidden_dim: int = 128):
    key = get_algorithm(name).name
    params = _runtime_params(key)
    effective_hidden = int(params.get("hidden_dim", hidden_dim))
    common = dict(input_dim=input_dim, n_actions=n_actions, learning_rate=learning_rate, gamma=gamma, hidden_dim=effective_hidden)
    if key == "double_dqn":
        return DoubleDQN(**common)
    if key == "cql":
        return CQLDoubleDQN(**common, cql_alpha=float(params.get("cql_alpha", 1.0)))
    if key == "iql":
        return IQLProxy(**common, expectile=float(params.get("iql_expectile", 0.7)), beta=float(params.get("iql_beta", 3.0)))
    if key == "bcq":
        return BCQProxy(**common, threshold=float(params.get("bcq_threshold", 0.05)))
    raise ValueError(key)


def train_step(model, algorithm: str, states, reward_matrix, next_states, dones) -> float:
    key = get_algorithm(algorithm).name
    if key == "double_dqn": return float(model.update_counterfactual(states, reward_matrix, next_states, dones))
    if key == "cql": return float(model.update_cql(states, reward_matrix, next_states, dones))
    if key == "iql": return float(model.update_iql(states, reward_matrix, next_states, dones))
    if key == "bcq": return float(model.update_bcq(states, reward_matrix, next_states, dones))
    raise ValueError(key)
