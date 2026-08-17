"""Reward configuration helpers."""
"""
backend/app/reward/reward_config.py

Configuration centrale du Reward System.

Toutes les récompenses, pénalités et paramètres
du Reward Shaping sont définis ici.
"""

from pydantic import BaseModel, Field


class RewardConfig(BaseModel):
    """
    Hyperparamètres du Reward System.
    """

    # -----------------------------------------------------
    # Incident Grade Reward
    # -----------------------------------------------------

    true_positive_reward: float = Field(
        default=20.0,
        description="Reward pour une vraie menace correctement traitée."
    )

    benign_positive_reward: float = Field(
        default=8.0,
        description="Reward pour une Benign Positive correctement fermée."
    )

    false_positive_reward: float = Field(
        default=10.0,
        description="Reward pour une False Positive correctement ignorée."
    )

    missed_true_positive_penalty: float = Field(
        default=-40.0,
        description="Pénalité si une vraie menace est ignorée."
    )

    false_positive_escalation_penalty: float = Field(
        default=-15.0,
        description="Pénalité pour une escalade inutile."
    )

    wrong_benign_penalty: float = Field(
        default=-8.0,
        description="Pénalité si une Benign Positive est escaladée."
    )

    # -----------------------------------------------------
    # Last Verdict Reward
    # -----------------------------------------------------

    malicious_bonus: float = Field(
        default=10.0
    )

    suspicious_bonus: float = Field(
        default=5.0
    )

    unknown_penalty: float = Field(
        default=-2.0
    )

    benign_penalty: float = Field(
        default=-5.0
    )

    # -----------------------------------------------------
    # Suspicion Level Reward
    # -----------------------------------------------------

    suspicion_high_bonus: float = Field(default=6.0)

    suspicion_medium_bonus: float = Field(default=3.0)

    suspicion_low_bonus: float = Field(default=1.0)

    # -----------------------------------------------------
    # Analyst Reward
    # -----------------------------------------------------

    analyst_bonus: float = Field(
        default=4.0
    )

    analyst_penalty: float = Field(
        default=-4.0
    )

    # -----------------------------------------------------
    # Latency
    # -----------------------------------------------------

    latency_weight: float = Field(
        default=0.10,
        ge=0
    )

    max_latency_penalty: float = Field(
        default=8.0,
        ge=0
    )

    # -----------------------------------------------------
    # Reward Clipping
    # -----------------------------------------------------

    min_reward: float = Field(default=-50.0)

    max_reward: float = Field(default=50.0)

    # -----------------------------------------------------
    # Enable Modules
    # -----------------------------------------------------

    enable_latency_reward: bool = True

    enable_analyst_reward: bool = True

    enable_reward_clipping: bool = True

    enable_verdict_reward: bool = True


reward_config = RewardConfig()