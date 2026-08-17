"""Evaluation service logic.

Provide basic evaluation helpers such as confusion matrix computation and
reward metric aggregation. These are intentionally small helpers that the
rest of the codebase can call for quick metrics.
"""

from typing import Sequence, Dict, Any


def confusion_matrix(preds: Sequence[int], targets: Sequence[int]) -> Dict[str, int]:
	"""Compute simple binary confusion counts for 0/1 labels.

	Returns counts for TP, TN, FP, FN. Works for larger integer labels in a
	best-effort way by treating matching/non-matching as positive/negative.
	"""
	tp = tn = fp = fn = 0
	for p, t in zip(preds, targets):
		if p == t:
			if p == 1:
				tp += 1
			else:
				tn += 1
		else:
			if p == 1:
				fp += 1
			else:
				fn += 1

	return {"tp": tp, "tn": tn, "fp": fp, "fn": fn}


def reward_summary(rewards: Sequence[float]) -> Dict[str, float]:
	if not rewards:
		return {"count": 0, "mean": 0.0, "sum": 0.0}

	count = len(rewards)
	total = sum(rewards)
	mean = total / count
	return {"count": count, "mean": mean, "sum": total}


__all__ = ["confusion_matrix", "reward_summary"]

