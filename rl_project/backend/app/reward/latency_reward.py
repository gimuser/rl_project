"""Latency reward logic."""
"""
backend/app/reward/latency_reward.py

Calcul de la pénalité liée au temps de réponse (MTTR).

Plus le temps de traitement est élevé,
plus la récompense diminue.
"""

from dataclasses import dataclass

from .reward_config import reward_config


@dataclass
class LatencyReward:
    """
    Calcule la pénalité de latence.
    """

    config = reward_config

    def compute(self, processing_time: float) -> float:
        """
        Parameters
        ----------
        processing_time : float
            Temps de traitement en secondes.

        Returns
        -------
        float
            Pénalité de latence.
        """

        # Si la pénalité est désactivée
        if not self.config.enable_latency_reward:
            return 0.0

        # Validation
        if processing_time is None:
            return 0.0

        if processing_time < 0:
            raise ValueError(
                "processing_time must be >= 0."
            )

        # -------------------------------------------
        # Temps excellent (<2 sec)
        # -------------------------------------------

        if processing_time <= 2:

            return 0.0

        # -------------------------------------------
        # Calcul linéaire
        # -------------------------------------------

        penalty = (
            processing_time
            * self.config.latency_weight
        )

        # -------------------------------------------
        # Limitation de la pénalité maximale
        # -------------------------------------------

        penalty = min(
            penalty,
            self.config.max_latency_penalty
        )

        return -penalty