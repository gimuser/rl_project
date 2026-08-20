"""Analyst workload reward logic."""
"""
backend/app/reward/analyst_reward.py

Calcul de la récompense liée à la charge de travail
des analystes SOC.

Le module utilise directement les informations
du dataset Microsoft Defender.
"""

from dataclasses import dataclass
from typing import Any, Dict

from .reward_config import reward_config


@dataclass
class AnalystReward:
    """
    Reward lié à la charge analyste.

    Plus l'agent automatise correctement
    les décisions, plus la récompense est élevée.
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

            Reward Analyst.
        """

        action_group = str(
            incident.get(
                "ActionGrouped",
                "Unknown"
            )
        ).strip()

        action_granular = str(
            incident.get(
                "ActionGranular",
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
        # Faible suspicion
        # Une fermeture automatique est préférable
        # ---------------------------------------------------

        if suspicion == "Low":

            if action == 0:
                reward += self.config.analyst_bonus

            else:
                reward += self.config.analyst_penalty

        # ---------------------------------------------------
        # Suspicion moyenne
        # Impact faible
        # ---------------------------------------------------

        elif suspicion == "Medium":

            if action == 0:
                reward += self.config.analyst_bonus / 2

            else:
                reward += self.config.analyst_penalty / 2

        # ---------------------------------------------------
        # Suspicion élevée
        # Une escalade est attendue
        # ---------------------------------------------------

        elif suspicion == "High":

            if action == 1:
                reward += self.config.analyst_bonus

            else:
                reward += self.config.analyst_penalty

        # ---------------------------------------------------
        # Analyse de ActionGrouped
        # ---------------------------------------------------

        if action_group != "Unknown":

            # Si le dataset indique déjà une action
            # proche de celle choisie,
            # on ajoute un léger bonus.

            if action == 1 and "Escal" in action_group:

                reward += 2.0

            elif action == 0 and (
                "Close" in action_group
                or "Ignore" in action_group
            ):

                reward += 2.0

        # ---------------------------------------------------
        # Analyse de ActionGranular
        # ---------------------------------------------------

        if action_granular != "Unknown":

            if action == 1:

                reward += 1.0

            else:

                reward += 0.5

        return reward