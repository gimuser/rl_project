import json
import os
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
)
from sklearn.preprocessing import OneHotEncoder

warnings.filterwarnings("ignore")

PROJECT = Path("/home/oualid/Desktop/RL_AGENT")
TRAIN_PATH = PROJECT / "data/processed/train_processed.csv"
TEST_PATH = PROJECT / "data/processed/test_processed.csv"
OUT = PROJECT / "models/state_quality_v2"

TARGET = "IncidentGrade"
INCIDENT_ID = "IncidentId"

CURRENT_STATE = [
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

# Columns that are never allowed into the RL state.
FORBIDDEN_STATE = {
    TARGET,
    INCIDENT_ID,
}

# Known post-resolution / target-like names that must never silently enter
# the state. This is intentionally conservative.
FORBIDDEN_NAME_PATTERNS = [
    "grade",
    "label",
    "target",
    "outcome",
    "resolution",
    "resolved",
    "verdict",
    "groundtruth",
    "ground_truth",
    "prediction",
    "predicted",
]

RANDOM_STATE = 42


def banner(text):
    print()
    print("=" * 70)
    print(text)
    print("=" * 70)


def safe_json_value(v):
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    return v


def normalize_name(name):
    return str(name).strip().lower().replace(" ", "_")


def forbidden_by_name(col):
    n = normalize_name(col)
    return any(pattern in n for pattern in FORBIDDEN_NAME_PATTERNS)


def main():
    banner("1. LOADING DATA")

    train = pd.read_csv(TRAIN_PATH)
    test = pd.read_csv(TEST_PATH)

    print(f"Train rows : {len(train):,}")
    print(f"Test rows  : {len(test):,}")
    print(f"Columns    : {len(train.columns)}")

    if TARGET not in train.columns or TARGET not in test.columns:
        raise RuntimeError("IncidentGrade missing")

    if INCIDENT_ID not in train.columns or INCIDENT_ID not in test.columns:
        raise RuntimeError("IncidentId missing")

    if list(train.columns) != list(test.columns):
        print("[WARNING] Train/test column order differs")

    banner("2. TARGET DISTRIBUTION")

    target_names = {
        0: "BenignPositive",
        1: "FalsePositive",
        2: "TruePositive",
        3: "Unknown",
    }

    target_train = train[TARGET].value_counts(dropna=False).sort_index()
    target_test = test[TARGET].value_counts(dropna=False).sort_index()

    print("\nTRAIN")
    for k, v in target_train.items():
        print(
            f"{k}: {target_names.get(k, str(k)):<18} "
            f"{v:,} ({100*v/len(train):.2f}%)"
        )

    print("\nTEST")
    for k, v in target_test.items():
        print(
            f"{k}: {target_names.get(k, str(k)):<18} "
            f"{v:,} ({100*v/len(test):.2f}%)"
        )

    banner("3. INCIDENT INTEGRITY")

    train_incidents = set(train[INCIDENT_ID].dropna().astype(str))
    test_incidents = set(test[INCIDENT_ID].dropna().astype(str))
    overlap = train_incidents & test_incidents

    print(f"TRAIN incidents : {len(train_incidents):,}")
    print(f"TEST incidents  : {len(test_incidents):,}")
    print(f"OVERLAP         : {len(overlap):,}")

    if overlap:
        print("[WARNING] Incident leakage exists in processed train/test")
    else:
        print("[OK] No incident overlap")

    banner("4. FULL 17-COLUMN HEALTH")

    health_rows = []

    for col in train.columns:
        s = train[col]

        row = {
            "feature": col,
            "dtype": str(s.dtype),
            "unique": int(s.nunique(dropna=False)),
            "missing": int(s.isna().sum()),
            "missing_pct": float(100 * s.isna().mean()),
            "train_only": False,
            "forbidden_target_or_id": col in FORBIDDEN_STATE,
            "forbidden_name_pattern": forbidden_by_name(col),
        }

        if pd.api.types.is_numeric_dtype(s):
            row["mean"] = float(s.mean())
            row["std"] = float(s.std())
            row["min"] = float(s.min())
            row["max"] = float(s.max())
        else:
            row["mean"] = None
            row["std"] = None
            row["min"] = None
            row["max"] = None

        health_rows.append(row)

    health = pd.DataFrame(health_rows)

    print(
        health[
            [
                "feature",
                "dtype",
                "unique",
                "missing",
                "missing_pct",
                "forbidden_target_or_id",
                "forbidden_name_pattern",
            ]
        ].to_string(index=False)
    )

    health.to_csv(OUT / "feature_health.csv", index=False)

    banner("5. CURRENT 11-FEATURE STATE CHECK")

    missing_current = [
        c for c in CURRENT_STATE
        if c not in train.columns
    ]

    if missing_current:
        raise RuntimeError(
            f"Current state features missing: {missing_current}"
        )

    current_stats = []

    for col in CURRENT_STATE:
        s = train[col]
        current_stats.append(
            {
                "feature": col,
                "unique": int(s.nunique(dropna=False)),
                "missing": int(s.isna().sum()),
                "missing_pct": float(100 * s.isna().mean()),
                "dtype": str(s.dtype),
            }
        )

    current_stats_df = pd.DataFrame(current_stats)

    print(current_stats_df.to_string(index=False))

    banner("6. TARGET ASSOCIATION SCREENING")

    # For each candidate feature, calculate a simple categorical
    # target-association score using normalized entropy reduction.
    #
    # This is diagnostic only. It does not create a model and does not
    # modify any dataset.

    association_rows = []

    for col in train.columns:
        if col in FORBIDDEN_STATE:
            continue

        tmp = train[[col, TARGET]].copy()

        # Missing values become an explicit category.
        tmp[col] = tmp[col].astype(str)
        tmp[TARGET] = tmp[TARGET].astype(str)

        global_probs = tmp[TARGET].value_counts(normalize=True)
        global_entropy = float(
            -(global_probs * np.log2(global_probs + 1e-12)).sum()
        )

        grouped = tmp.groupby(col, observed=False)[TARGET]

        conditional_entropy = 0.0

        for _, labels in grouped:
            p = labels.value_counts(normalize=True)
            entropy = float(
                -(p * np.log2(p + 1e-12)).sum()
            )
            conditional_entropy += (
                len(labels) / len(tmp)
            ) * entropy

        information_gain = global_entropy - conditional_entropy

        association_rows.append(
            {
                "feature": col,
                "information_gain": float(information_gain),
                "unique": int(train[col].nunique(dropna=False)),
                "missing_pct": float(100 * train[col].isna().mean()),
                "forbidden": bool(
                    col in FORBIDDEN_STATE or forbidden_by_name(col)
                ),
            }
        )

    association = (
        pd.DataFrame(association_rows)
        .sort_values("information_gain", ascending=False)
    )

    print(
        association[
            [
                "feature",
                "information_gain",
                "unique",
                "missing_pct",
                "forbidden",
            ]
        ].to_string(index=False)
    )

    association.to_csv(
        OUT / "target_association.csv",
        index=False,
    )

    banner("7. CANDIDATE STATE CONSTRUCTION")

    safe_candidates = []

    for col in train.columns:
        if col in FORBIDDEN_STATE:
            continue

        if forbidden_by_name(col):
            print(
                f"[EXCLUDED] {col}: suspicious target/post-resolution name"
            )
            continue

        if train[col].isna().mean() > 0.50:
            print(
                f"[EXCLUDED] {col}: >50% missing"
            )
            continue

        if train[col].nunique(dropna=False) <= 1:
            print(
                f"[EXCLUDED] {col}: constant"
            )
            continue

        safe_candidates.append(col)

    # Keep the existing 11 state features first.
    expanded_state = list(CURRENT_STATE)

    # Add only additional safe features ranked by information gain.
    ranked = association[
        (~association["forbidden"])
        & (association["feature"].isin(safe_candidates))
    ]

    for col in ranked["feature"]:
        if col not in expanded_state:
            expanded_state.append(col)

    print("\nCURRENT STATE:")
    for c in CURRENT_STATE:
        print(f"  - {c}")

    print("\nSAFE CANDIDATES:")
    for c in safe_candidates:
        marker = "*" if c in expanded_state else " "
        print(f" {marker} {c}")

    print("\nEXPANDED CANDIDATE STATE:")
    for c in expanded_state:
        print(f"  - {c}")

    with open(OUT / "candidate_state.json", "w") as f:
        json.dump(
            {
                "current_state": CURRENT_STATE,
                "safe_candidates": safe_candidates,
                "expanded_candidate_state": expanded_state,
                "forbidden": sorted(FORBIDDEN_STATE),
            },
            f,
            indent=2,
        )

    banner("8. SUPERVISED BASELINE — CURRENT 11 FEATURES")

    def evaluate_state(features, name):
        print()
        print(f"===== {name} =====")
        print(f"Features: {len(features)}")

        X_train = train[features].copy()
        X_test = test[features].copy()

        y_train = train[TARGET]
        y_test = test[TARGET]

        categorical = [
            c for c in features
            if (
                X_train[c].dtype == "object"
                or X_train[c].nunique(dropna=False) < 100
            )
        ]

        numeric = [
            c for c in features
            if c not in categorical
        ]

        transformers = []

        if categorical:
            transformers.append(
                (
                    "cat",
                    OneHotEncoder(
                        handle_unknown="ignore",
                        min_frequency=2,
                    ),
                    categorical,
                )
            )

        if numeric:
            transformers.append(
                ("num", "passthrough", numeric)
            )

        preprocessor = ColumnTransformer(
            transformers=transformers,
            remainder="drop",
        )

        X_train_enc = preprocessor.fit_transform(X_train)
        X_test_enc = preprocessor.transform(X_test)

        print(
            f"Encoded train shape: {X_train_enc.shape}"
        )
        print(
            f"Encoded test shape : {X_test_enc.shape}"
        )

        clf = RandomForestClassifier(
            n_estimators=200,
            max_depth=20,
            min_samples_leaf=5,
            class_weight="balanced_subsample",
            n_jobs=-1,
            random_state=RANDOM_STATE,
        )

        clf.fit(X_train_enc, y_train)
        pred = clf.predict(X_test_enc)

        accuracy = accuracy_score(y_test, pred)
        balanced = balanced_accuracy_score(y_test, pred)
        macro_f1 = f1_score(
            y_test,
            pred,
            average="macro",
            zero_division=0,
        )

        report = classification_report(
            y_test,
            pred,
            target_names=[
                target_names[i]
                for i in sorted(target_names)
            ],
            output_dict=True,
            zero_division=0,
        )

        cm = confusion_matrix(
            y_test,
            pred,
            labels=[0, 1, 2, 3],
        )

        print(f"Accuracy          : {accuracy:.4f}")
        print(f"Balanced accuracy : {balanced:.4f}")
        print(f"Macro F1          : {macro_f1:.4f}")

        print("\nCLASSIFICATION REPORT")
        print(
            classification_report(
                y_test,
                pred,
                target_names=[
                    target_names[i]
                    for i in sorted(target_names)
                ],
                zero_division=0,
            )
        )

        print("CONFUSION MATRIX")
        print(cm)

        tp_recall = float(
            report["TruePositive"]["recall"]
        )

        unknown_f1 = float(
            report["Unknown"]["f1-score"]
        )

        result = {
            "name": name,
            "features": features,
            "accuracy": float(accuracy),
            "balanced_accuracy": float(balanced),
            "macro_f1": float(macro_f1),
            "true_positive_recall": tp_recall,
            "unknown_f1": unknown_f1,
            "classification_report": report,
            "confusion_matrix": cm.tolist(),
            "incident_overlap": len(overlap),
        }

        return result

    current_result = evaluate_state(
        CURRENT_STATE,
        "current_11_features",
    )

    with open(
        OUT / "current_state_baseline.json",
        "w",
    ) as f:
        json.dump(current_result, f, indent=2)

    banner("9. EXPANDED SAFE STATE TEST")

    # To keep this diagnostic bounded, test the current state plus the
    # strongest additional safe features. We do not blindly add every
    # high-cardinality column.
    #
    # Select up to 8 additional features by information gain.
    additions = []

    for col in ranked["feature"]:
        if col not in CURRENT_STATE:
            additions.append(col)

        if len(additions) >= 8:
            break

    expanded_test_state = CURRENT_STATE + additions

    print("Additional features selected:")
    for c in additions:
        print(f"  + {c}")

    expanded_result = evaluate_state(
        expanded_test_state,
        "expanded_candidate_state",
    )

    with open(
        OUT / "expanded_state_baseline.json",
        "w",
    ) as f:
        json.dump(expanded_result, f, indent=2)

    banner("10. STATE COMPARISON")

    comparison = pd.DataFrame(
        [
            {
                "state": "current_11_features",
                "n_features": len(CURRENT_STATE),
                "accuracy": current_result["accuracy"],
                "balanced_accuracy": current_result[
                    "balanced_accuracy"
                ],
                "macro_f1": current_result["macro_f1"],
                "true_positive_recall": current_result[
                    "true_positive_recall"
                ],
                "unknown_f1": current_result["unknown_f1"],
            },
            {
                "state": "expanded_candidate_state",
                "n_features": len(expanded_test_state),
                "accuracy": expanded_result["accuracy"],
                "balanced_accuracy": expanded_result[
                    "balanced_accuracy"
                ],
                "macro_f1": expanded_result["macro_f1"],
                "true_positive_recall": expanded_result[
                    "true_positive_recall"
                ],
                "unknown_f1": expanded_result["unknown_f1"],
            },
        ]
    )

    print(comparison.to_string(index=False))

    comparison.to_csv(
        OUT / "state_comparison.csv",
        index=False,
    )

    banner("11. FINAL STATE-QUALITY GATE")

    current_f1 = current_result["macro_f1"]
    expanded_f1 = expanded_result["macro_f1"]

    current_tp = current_result["true_positive_recall"]
    expanded_tp = expanded_result["true_positive_recall"]

    current_unknown = current_result["unknown_f1"]
    expanded_unknown = expanded_result["unknown_f1"]

    improvement_f1 = expanded_f1 - current_f1
    improvement_tp = expanded_tp - current_tp
    improvement_unknown = expanded_unknown - current_unknown

    print(
        f"Macro-F1 improvement       : {improvement_f1:+.4f}"
    )
    print(
        f"TP recall improvement      : {improvement_tp:+.4f}"
    )
    print(
        f"Unknown F1 improvement     : {improvement_unknown:+.4f}"
    )

    # This gate is deliberately conservative.
    #
    # We DO NOT authorize DQN training merely because accuracy improves.
    # We require:
    #   - zero incident overlap for final RL evaluation
    #   - improved macro F1
    #   - improved TP recall
    #   - no catastrophic Unknown degradation
    #
    # The actual thresholds are diagnostic gates, not claims that these
    # values are universally sufficient.

    gate_zero_leakage = len(overlap) == 0
    gate_f1 = expanded_f1 >= current_f1 + 0.03
    gate_tp = expanded_tp >= current_tp + 0.10
    gate_unknown = expanded_unknown >= max(
        0.05,
        current_unknown - 0.02,
    )

    print()
    print(
        "[OK]" if gate_zero_leakage
        else "[FAIL]",
        "Zero incident overlap"
    )

    print(
        "[OK]" if gate_f1
        else "[FAIL]",
        "Macro-F1 improvement >= +0.03"
    )

    print(
        "[OK]" if gate_tp
        else "[FAIL]",
        "TruePositive recall improvement >= +0.10"
    )

    print(
        "[OK]" if gate_unknown
        else "[FAIL]",
        "Unknown F1 not catastrophically degraded"
    )

    authorization = (
        gate_zero_leakage
        and gate_f1
        and gate_tp
        and gate_unknown
    )

    summary = {
        "read_only": True,
        "dqn_training_started": False,
        "datasets_modified": False,
        "rl_files_modified": False,
        "train_rows": len(train),
        "test_rows": len(test),
        "train_incidents": len(train_incidents),
        "test_incidents": len(test_incidents),
        "incident_overlap": len(overlap),
        "current_state": CURRENT_STATE,
        "expanded_state": expanded_test_state,
        "current_result": current_result,
        "expanded_result": expanded_result,
        "gate": {
            "zero_incident_overlap": gate_zero_leakage,
            "macro_f1_improvement": gate_f1,
            "tp_recall_improvement": gate_tp,
            "unknown_not_degraded": gate_unknown,
        },
        "dqn_training_authorized": authorization,
    }

    with open(
        OUT / "state_quality_v2_summary.json",
        "w",
    ) as f:
        json.dump(summary, f, indent=2)

    banner("12. FINAL RESULT")

    if authorization:
        print("[PASS] STATE-QUALITY GATE PASSED")
        print()
        print("The expanded state is sufficiently better for")
        print("the NEXT controlled RL experiment.")
        print()
        print("IMPORTANT:")
        print("  This script did NOT train the DQN.")
        print("  A separate training script should be used next.")
    else:
        print("[BLOCKED] STATE-QUALITY GATE FAILED")
        print()
        print("DO NOT TRAIN THE DQN YET.")
        print()
        if not gate_zero_leakage:
            print(
                "- Fix incident-level train/test leakage first."
            )
        if not gate_f1:
            print(
                "- Expanded state did not improve Macro-F1 enough."
            )
        if not gate_tp:
            print(
                "- TruePositive recall remains insufficient."
            )
        if not gate_unknown:
            print(
                "- Unknown detection degraded too much."
            )

    print()
    print("Reports:")
    for p in sorted(OUT.iterdir()):
        if p.is_file():
            print(f"  {p}")

    print()
    print("======================================================================")
    print(" READ-ONLY STATE QUALITY ANALYSIS FINISHED")
    print("======================================================================")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print()
        print("======================================================================")
        print("[FAILED] STATE QUALITY ANALYSIS")
        print("======================================================================")
        print(type(exc).__name__ + ":", exc)
        print()
        print("NO RL FILES WERE MODIFIED.")
        print("NO SOURCE DATASETS WERE MODIFIED.")
        print("NO DQN TRAINING WAS STARTED.")
        sys.exit(1)
