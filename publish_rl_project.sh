#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="/home/oualid/Desktop/Data_mission/RL_Agent"
REMOTE_NAME="rl-project"
REMOTE_URL="https://github.com/gimuser/rl_project.git"
REPO_FULL="gimuser/rl_project"

cd "$REPO_DIR"

echo "============================================================"
echo "PUBLISH RL PROJECT"
echo "============================================================"
echo "LOCAL : $REPO_DIR"
echo "REMOTE: $REPO_FULL"
echo "PUBLIC: YES"
echo
echo "DATASETS WILL NOT BE PUSHED."
echo "============================================================"


# ============================================================
# REQUIRE TOOLS
# ============================================================

command -v git >/dev/null 2>&1 || {
    echo "ERROR: git is required."
    exit 1
}

command -v gh >/dev/null 2>&1 || {
    echo "ERROR: GitHub CLI (gh) is required."
    exit 1
}

gh auth status >/dev/null 2>&1 || {
    echo "ERROR: gh is not authenticated."
    echo "Run: gh auth login"
    exit 1
}


# ============================================================
# VERIFY REPOSITORY
# ============================================================

git rev-parse --is-inside-work-tree >/dev/null 2>&1 || {
    echo "ERROR: not a git repository."
    exit 1
}


# ============================================================
# CREATE .gitignore FOR LARGE DATA
# ============================================================

cat > .gitignore <<'EOF'
# ============================================================
# LARGE DATASETS — NEVER PUSH
# ============================================================

data/raw/
data/external/
data/interim/
data/processed/*.csv

data/rl_incident/*.csv
data/rl_incident/*.txt
data/rl_incident/*.json

data_alert/*.csv
data_alert/*.json

# Local preprocessing artifacts
.processed_work/
data_finished/
start_point_*.csv
incident_*.csv
train_processed.csv
test_processed.csv
live_80_*.csv

# ============================================================
# LARGE GENERATED MODEL / EVALUATION ARTIFACTS
# ============================================================

models/*.pt
models/*.pth
models/*.onnx

models/*predictions*
models/*.jsonl

models/checkpoints/
models/experiments/

# Keep lightweight model metadata if desired
!models/.gitkeep

# ============================================================
# LOCAL TEMPORARY FILES
# ============================================================

*.sqlite
*.db
*.log

.health_audit_work/
.leakage_fix_tmp/
.live_80_work/
.start_point_work/
EOF

echo
echo "[OK] .gitignore updated."


# ============================================================
# IMPORTANT:
# Remove large data files from Git INDEX only.
#
# This does NOT delete local files.
# ============================================================

echo
echo "============================================================"
echo "REMOVE DATA FROM GIT INDEX"
echo "============================================================"

git rm -r --cached --ignore-unmatch \
    data/raw \
    data/external \
    data/interim \
    data/processed \
    data/rl_incident \
    data_alert \
    2>/dev/null || true

git rm --cached --ignore-unmatch \
    train_processed.csv \
    test_processed.csv \
    incident_Train.csv \
    incident_Test.csv \
    live_80_source.csv \
    live_80_processed.csv \
    live_80_mapping.csv \
    2>/dev/null || true

echo
echo "[OK] large data removed from Git tracking."
echo "[OK] local files remain on disk."


# ============================================================
# REMOVE LARGE GENERATED MODEL ARTIFACTS FROM GIT
# ============================================================

git rm -r --cached --ignore-unmatch \
    models/checkpoints \
    models/experiments \
    2>/dev/null || true

git rm --cached --ignore-unmatch \
    models/real_dqn_agent.pt \
    models/test_predictions.csv \
    models/real_test_predictions.jsonl \
    2>/dev/null || true

echo
echo "[OK] large generated model/evaluation files excluded."


# ============================================================
# SAFETY CHECK — SHOW WHAT WILL BE COMMITTED
# ============================================================

echo
echo "============================================================"
echo "CHECK LARGE FILES"
echo "============================================================"

echo
echo "Tracked files larger than 20 MB:"
find . -type f -not -path './.git/*' \
    -size +20M \
    -print \
    | sort || true

echo
echo "These files should normally be excluded by .gitignore."
echo


# ============================================================
# COMMIT CURRENT PROJECT STATE
# ============================================================

git add -A

echo
echo "============================================================"
echo "STAGED SUMMARY"
echo "============================================================"

git status --short

echo
echo "============================================================"
echo "CREATE COMMIT"
echo "============================================================"

if git diff --cached --quiet; then
    echo "[OK] Nothing new to commit."
else
    git commit -m "Create rl_project baseline with hardened data pipeline" || {
        echo "ERROR: commit failed."
        exit 1
    }
fi


# ============================================================
# CREATE NEW PUBLIC GITHUB REPOSITORY
# ============================================================

echo
echo "============================================================"
echo "CREATE PUBLIC GITHUB REPOSITORY"
echo "============================================================"

if gh repo view "$REPO_FULL" >/dev/null 2>&1; then
    echo "[OK] $REPO_FULL already exists."
else
    gh repo create "$REPO_FULL" \
        --public \
        --description "Reinforcement Learning Agent for autonomous alert triage and analyst workload optimization" \
        || {
            echo "ERROR: could not create GitHub repository."
            exit 1
        }

    echo "[OK] public repository created."
fi


# ============================================================
# REMOTE
# ============================================================

echo
echo "============================================================"
echo "CONFIGURE REMOTE"
echo "============================================================"

if git remote get-url "$REMOTE_NAME" >/dev/null 2>&1; then
    git remote set-url "$REMOTE_NAME" "$REMOTE_URL"
else
    git remote add "$REMOTE_NAME" "$REMOTE_URL"
fi

echo "[OK] remote: $REMOTE_NAME"
echo "[OK] URL   : $REMOTE_URL"


# ============================================================
# PUSH
# ============================================================

echo
echo "============================================================"
echo "PUSH PROJECT"
echo "============================================================"

BRANCH="$(git branch --show-current)"

if [[ -z "$BRANCH" ]]; then
    BRANCH="main"
    git branch -M main
    BRANCH="main"
fi

git push -u "$REMOTE_NAME" "$BRANCH"

echo
echo "============================================================"
echo "VERIFY REMOTE"
echo "============================================================"

gh repo view "$REPO_FULL" \
    --json nameWithOwner,isPrivate,url,defaultBranchRef \
    --jq '"Repository: \(.nameWithOwner)\nPublic: \(.isPrivate | not)\nURL: \(.url)\nDefault branch: \(.defaultBranchRef.name)"'


# ============================================================
# FINAL LOCAL STATUS
# ============================================================

echo
echo "============================================================"
echo "FINAL STATUS"
echo "============================================================"

git status --short

echo
echo "============================================================"
echo "SUCCESS"
echo "============================================================"
echo
echo "PUBLIC REPOSITORY:"
echo "  https://github.com/gimuser/rl_project"
echo
echo "DATASETS WERE NOT PUSHED."
echo "PROJECT CODE WAS PUSHED."
echo "LOCAL DATA REMAINS ON DISK."
echo "============================================================"
