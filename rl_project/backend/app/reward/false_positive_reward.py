"""False-positive reward logic."""
"""
backend/app/reward/false_positive_reward.py

Calcul de la pénalité spécifique liée aux False Positives.

Ce module ne regarde PAS IncidentGrade.
Il se base uniquement sur :

    - LastVerdict
    - SuspicionLevel

Son objectif est de modéliser le coût métier
d'une escalade inutile vers un analyste SOC.
"""

from dataclasses import dataclass
from typing import Any, Dict

from .reward_config import reward_config


@dataclass
class FalsePositiveReward:
    """
    Calcule la pénalité supplémentaire
    liée aux faux positifs.

    Ce module est indépendant de SeverityReward.
    """

    config = reward_config

    def compute(
        self,
        incident: Dict[str, Any],
        action: int
    ) -> float:
        """
        Parameters
        ----------
        incident : dict
            Ligne du dataset.

        action : int

            0 -> Close / Ignore

            1 -> Escalate

        Returns
        -------
        float
            Reward/Penalty.
        """

        verdict = str(
            incident.get(
                "LastVerdict",
                "Unknown"
            )
        ).strip()

        suspicion = str(
            incident.get(
                "SuspicionLevel",
                "Unknown"
            )
        ).strip()

        reward = 0.0

        # ---------------------------------------------------
        # Cas 1 :
        # Verdict Benign
        # Une escalade est inutile.
        # ---------------------------------------------------

        if verdict == "Benign":

            if action == 1:

                reward += self.config.false_positive_escalation_penalty

            return reward

        # ---------------------------------------------------
        # Cas 2 :
        # Verdict Unknown
        # On pénalise légèrement
        # une escalade.
        # ---------------------------------------------------

        if verdict == "Unknown":

            if action == 1:

                reward += self.config.unknown_penalty

            return reward

        # ---------------------------------------------------
        # Cas 3 :
        # Suspicion faible
        # ---------------------------------------------------

        if suspicion == "Low":

            if action == 1:

                reward -= 2.0

            return reward

        # ---------------------------------------------------
        # Cas 4 :
        # Suspicion moyenne
        # ---------------------------------------------------

        if suspicion == "Medium":

            return 0.0

        # ---------------------------------------------------
        # Cas 5 :
        # Suspicion élevée
        # Une escalade est normale.
        # ---------------------------------------------------

        if suspicion == "High":

            if action == 1:

                reward += 1.0

            return reward

        return reward
