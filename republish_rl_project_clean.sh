#!/usr/bin/env bash
set -euo pipefail

REPO="/home/oualid/Desktop/Data_mission/RL_Agent"
REMOTE="rl-project"
URL="https://github.com/gimuser/rl_project.git"

cd "$REPO"

echo "============================================================"
echo "CLEAN REPUBLISH — rl_project"
echo "============================================================"

command -v git >/dev/null 2>&1 || {
    echo "ERROR: git not installed"
    exit 1
}

command -v gh >/dev/null 2>&1 || {
    echo "ERROR: gh not installed"
    exit 1
}

# ------------------------------------------------------------
# Verify clean ignore rules
# ------------------------------------------------------------

cat > .gitignore <<'EOF'
# Large datasets
data/raw/
data/external/
data/interim/
data/processed/*.csv
data/rl_incident/*.csv
data/rl_incident/*.txt
data/rl_incident/*.json
data_alert/*.csv
data_alert/*.json

# Local/generated datasets
.processed_work/
start_point_*.csv
incident_*.csv
train_processed.csv
test_processed.csv
live_80_*.csv

# Large models / evaluation artifacts
models/*.pt
models/*.pth
models/*.onnx
models/*predictions*
models/*.jsonl
models/checkpoints/
models/experiments/

# Temporary files
*.sqlite
*.db
*.log
.health_audit_work/
.leakage_fix_tmp/
.live_80_work/
.start_point_work/
EOF

# ------------------------------------------------------------
# Remove ignored data from the current index
# ------------------------------------------------------------

git rm -r --cached --ignore-unmatch \
    data/processed \
    data/rl_incident \
    data_alert \
    models/checkpoints \
    models/experiments \
    2>/dev/null || true

git rm --cached --ignore-unmatch \
    models/real_dqn_agent.pt \
    models/test_predictions.csv \
    models/real_test_predictions.jsonl \
    2>/dev/null || true

git add -A

# ------------------------------------------------------------
# Create a completely clean orphan branch.
# This removes the old heavy history from what gets pushed.
# ------------------------------------------------------------

git checkout --orphan rl_project_clean

git reset

git add -A

echo
echo "============================================================"
echo "CHECKING TRACKED LARGE FILES"
echo "============================================================"

LARGE_FILES="$(git ls-files -z | while IFS= read -r -d '' f; do
    if [[ -f "$f" ]]; then
        size=$(stat -c%s "$f")
        if (( size > 20 * 1024 * 1024 )); then
            printf '%s\n' "$f"
        fi
    fi
done)"

if [[ -n "$LARGE_FILES" ]]; then
    echo "ERROR: files >20MB are still tracked:"
    echo "$LARGE_FILES"
    exit 1
fi

echo "[OK] no tracked files larger than 20 MB."

# ------------------------------------------------------------
# Commit clean project snapshot
# ------------------------------------------------------------

git config user.name >/dev/null 2>&1 || \
    git config user.name "gimuser"

git config user.email >/dev/null 2>&1 || \
    git config user.email "213307588+gimuser@users.noreply.github.com"

git commit -m "Initial clean rl_project baseline"

# ------------------------------------------------------------
# Rename clean branch to main
# ------------------------------------------------------------

git branch -M main

# ------------------------------------------------------------
# Configure remote
# ------------------------------------------------------------

if git remote get-url "$REMOTE" >/dev/null 2>&1; then
    git remote set-url "$REMOTE" "$URL"
else
    git remote add "$REMOTE" "$URL"
fi

# ------------------------------------------------------------
# Push only the clean snapshot
# ------------------------------------------------------------

echo
echo "============================================================"
echo "PUSHING CLEAN HISTORY"
echo "============================================================"

git push -u "$REMOTE" main --force

echo
echo "============================================================"
echo "VERIFY"
echo "============================================================"

gh repo view gimuser/rl_project \
    --json nameWithOwner,isPrivate,size,defaultBranchRef,url \
    --jq '"Repository: \(.nameWithOwner)\nPublic: \(.isPrivate | not)\nSize: \(.size) KB\nBranch: \(.defaultBranchRef.name)\nURL: \(.url)"'

echo
echo "============================================================"
echo "SUCCESS"
echo "============================================================"
echo "https://github.com/gimuser/rl_project"
echo
echo "Large datasets were not pushed."
echo "Old heavy Git history was not pushed."
echo "============================================================"
