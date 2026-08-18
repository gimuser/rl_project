#!/usr/bin/env python3
"""Recalculate and persist the Additional Metrics report after training/live evaluation."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.services.additional_metrics_service import calculate_additional_metrics  # noqa: E402


if __name__ == "__main__":
    result = calculate_additional_metrics(persist=True)
    print(json.dumps(result, indent=2, default=str))
    print(f"\nSaved: {ROOT / 'models' / 'additional_metrics.json'}")
