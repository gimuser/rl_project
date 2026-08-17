from __future__ import annotations

FEATURES = [
    "Category",
    "MitreTechniques",
    "EntityType",
    "EvidenceRole",
    "ThreatFamily",
    "OSFamily",
    "SuspicionLevel",
    "hour",
    "day",
    "month",
    "is_weekend",
]

ACTIONS = {
    0: "allow",
    1: "block",
    2: "human_review",
}

LABELS = {
    0: "BenignPositive",
    1: "FalsePositive",
    2: "TruePositive",
    3: "Unknown",
}

# Counterfactual reward.
#
# The target IncidentGrade is NEVER supplied to the neural network.
# It is used only to calculate the historical/counterfactual reward.
#
# Columns:
#   action 0 = allow
#   action 1 = block
#   action 2 = human_review
REWARD_TABLE = {
    0: [2.00, -2.50, 0.10],   # BenignPositive
    1: [2.00, -2.00, 0.10],   # FalsePositive
    2: [-3.00, 3.00, 0.75],   # TruePositive
    3: [-1.00, 0.50, 1.00],   # Unknown
}

ID_COLUMN = "IncidentId"
TARGET_COLUMN = "IncidentGrade"
TIMESTAMP_COLUMN = "Timestamp"

DEFAULT_EPOCHS = 10
DEFAULT_BATCH_SIZE = 512
DEFAULT_GAMMA = 0.95
DEFAULT_LR = 0.0003

# Epsilon is intentionally small.
# The offline trainer learns all counterfactual actions directly, so
# exploration is not the mechanism used to discover actions.
EPSILON_START = 0.05
EPSILON_END = 0.01

SEED = 42
