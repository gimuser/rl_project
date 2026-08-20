from __future__ import annotations

from typing import Dict

import torch
from torch import nn


class CategoricalEmbeddingNetwork(nn.Module):
    """
    Embedding-based Q-network.

    Continuous/numerical features are projected directly.
    Categorical features are embedded using train-only vocabularies.
    """

    def __init__(
        self,
        categorical_cardinalities: Dict[str, int],
        numerical_dim: int,
        n_actions: int,
        embedding_dim: int = 16,
        hidden_dim: int = 128,
    ):
        super().__init__()

        self.categorical_names = list(categorical_cardinalities.keys())

        self.embeddings = nn.ModuleDict()

        for name, cardinality in categorical_cardinalities.items():
            self.embeddings[name] = nn.Embedding(
                max(2, int(cardinality)),
                embedding_dim,
            )

        input_dim = (
            len(categorical_cardinalities) * embedding_dim
            + numerical_dim
        )

        self.network = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, n_actions),
        )

    def forward(
        self,
        categorical_inputs: Dict[str, torch.Tensor],
        numerical_inputs: torch.Tensor,
    ) -> torch.Tensor:

        pieces = []

        for name in self.categorical_names:
            x = categorical_inputs[name].long()
            pieces.append(self.embeddings[name](x))

        if numerical_inputs.numel() > 0:
            pieces.append(numerical_inputs.float())

        x = torch.cat(pieces, dim=1)

        return self.network(x)


class MLPQNetwork(nn.Module):
    """
    Generic numerical Q-network.
    """

    def __init__(
        self,
        input_dim: int,
        n_actions: int,
        hidden_dim: int = 128,
    ):
        super().__init__()

        self.network = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, n_actions),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.network(x)


# ==========================================================================
# BACKWARD-COMPATIBLE QNetwork API
# ==========================================================================
#
# Existing application code imports:
#
#     from app.rl_agent.networks import QNetwork
#
# Keep this public symbol available. The authoritative training model
# remains DoubleDQN in dqn.py.
# ==========================================================================

class QNetwork(nn.Module):
    """
    Backward-compatible DQN Q-network.

    This matches the application's historical constructor:
        QNetwork(state_size, action_size)

    The architecture is intentionally simple and compatible with the
    accepted 13-dimensional RL state.
    """

    def __init__(
        self,
        state_size: int,
        action_size: int,
        hidden_size: int = 128,
    ):
        super().__init__()

        self.model = nn.Sequential(
            nn.Linear(state_size, hidden_size),
            nn.ReLU(),
            nn.Linear(hidden_size, hidden_size),
            nn.ReLU(),
            nn.Linear(hidden_size, action_size),
        )

    def forward(self, x):
        return self.model(x)


