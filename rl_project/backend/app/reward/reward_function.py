"""Core reward function logic."""
"""
backend/app/reward/reward_function.py

Reward Engine principal.

Ce module combine toutes les composantes du Reward System
et retourne la récompense finale utilisée par
l'environnement Gymnasium.
"""

from typing import Any, Dict

from .reward_config import reward_config

from .severity_reward import SeverityReward
from .false_positive_reward import FalsePositiveReward
from .analyst_reward import AnalystReward
from .latency_reward import LatencyReward


class RewardFunction:
    """
    Reward Engine principal.

    Combine :

        - Severity Reward

        - False Positive Reward

        - Analyst Reward

        - Latency Reward

    Puis applique un clipping.
    """

    def __init__(self):

        self.config = reward_config

        self.severity_reward = SeverityReward()

        self.false_positive_reward = FalsePositiveReward()

        self.analyst_reward = AnalystReward()

        self.latency_reward = LatencyReward()

    def compute_reward(
        self,
        incident: Dict[str, Any],
        action: int,
        processing_time: float
    ) -> float:
        """
        Parameters
        ----------
        incident

            Ligne du dataset Microsoft.

        action

            0 = Close / Ignore

            1 = Escalate

        processing_time

            Temps de traitement (secondes).

        Returns
        -------
        float

            Reward final.
        """

        reward = 0.0

        # -------------------------------------------
        # Severity Reward
        # -------------------------------------------

        reward += self.severity_reward.compute(
            incident=incident,
            action=action
        )

        # -------------------------------------------
        # False Positive Reward
        # -------------------------------------------

        reward += self.false_positive_reward.compute(
            incident=incident,
            action=action
        )

        # -------------------------------------------
        # Analyst Reward
        # -------------------------------------------

        if self.config.enable_analyst_reward:

            reward += self.analyst_reward.compute(
                incident=incident,
                action=action
            )

        # -------------------------------------------
        # Latency Reward
        # -------------------------------------------

        reward += self.latency_reward.compute(
            processing_time=processing_time
        )

        # -------------------------------------------
        # Reward Clipping
        # -------------------------------------------

        if self.config.enable_reward_clipping:

            reward = max(

                self.config.min_reward,

                min(
                    reward,
                    self.config.max_reward
                )

            )

        return reward

    def __call__(
        self,
        incident: Dict[str, Any],
        action: int,
        processing_time: float
    ) -> float:
        """
        Permet d'utiliser directement
        l'objet RewardFunction.

        Exemple

        reward = reward_engine(
            incident,
            action,
            latency
        )
        """

        return self.compute_reward(

            incident=incident,

            action=action,

            processing_time=processing_time

        )
