#!/usr/bin/env bash

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT" || exit 1

while true; do
    clear

    echo "============================================================"
    echo " RL_Agent — TRAINING MONITOR"
    echo "============================================================"
    echo "Time: $(date '+%Y-%m-%d %H:%M:%S')"
    echo

    echo "== SYSTEM =="
    free -h
    echo

    echo "== CPU / MEMORY =="
    ps -eo pid,ppid,%cpu,%mem,rss,vsz,etime,cmd --sort=-%cpu \
        | grep -E 'python|uvicorn|sequential_experiment|rl_agent' \
        | grep -v grep \
        | head -15
    echo

    echo "== TRAINING PROCESSES =="
    pgrep -af 'sequential_experiment|train|rl_agent' || echo "No training process detected."
    echo

    echo "== RECENT TRAINING OUTPUT =="
    if [ -f /tmp/rl_agent_training.log ]; then
        tail -25 /tmp/rl_agent_training.log
    elif [ -f /tmp/rl_agent_backend.log ]; then
        tail -25 /tmp/rl_agent_backend.log
    else
        echo "No training log found yet."
    fi

    echo
    echo "== MODEL ARTIFACTS =="
    find models -maxdepth 2 -type f -printf '%TY-%Tm-%Td %TH:%TM:%TS  %10s  %p\n' \
        2>/dev/null | sort -r | head -20

    echo
    echo "============================================================"
    echo "Refreshing every 5 seconds — CTRL+C to stop monitor"
    echo "============================================================"

    sleep 5
done
