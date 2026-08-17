#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

printf '\n==============================================================\n'
printf ' RL AGENT — GUIDE DATA UPDATE RUNNER\n'
printf '==============================================================\n'
printf 'Project: %s\n' "$PROJECT_ROOT"
printf 'Branch : '; git branch --show-current || true
printf '\n'

python3 scripts/update_soc_data.py

printf '\n==============================================================\n'
printf ' RUNNER FINISHED\n'
printf '==============================================================\n'
printf 'Train: data/rl_incident/train_incident.csv\n'
printf 'Test : data/rl_incident/test_incident.csv\n'
printf 'Live : data_alert/live_source.csv + data_alert/live_processed.csv\n'
printf 'Report: data/rl_incident/split_report.json\n'
printf '\n'
