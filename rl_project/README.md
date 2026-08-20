# SOAR-RL-Agent

Reinforcement Learning agent for autonomous security-alert triage and analyst workload optimization in a SOAR-oriented pipeline.

## 1. Project overview

SOAR-RL-Agent is a full-stack research and validation project combining a security-alert data pipeline, a Gymnasium-compatible RL environment, reward modeling, offline RL, a FastAPI backend, MongoDB persistence, and a web dashboard.

The central task is to learn a decision policy that maps an incoming security-alert state to an operational triage action such as **allow**, **block**, or **human_review**. The system uses a contextual, one-step decision setting: the agent observes the alert state, evaluates the available actions through the project reward model, and selects the action with the best expected utility.

The repository contains the complete application stack used for validation:

- **Data layer:** preprocessing, normalization, feature engineering, encoding, dataset validation and export.
- **RL layer:** state representation, Gymnasium environment, reward system, training, evaluation and inference.
- **Backend:** FastAPI services and API endpoints for alerts, decisions, training, evaluation, metrics and live cycles.
- **Database:** MongoDB for live alerts, alert activity, reviews, analysts and related operational state.
- **Frontend:** React/Vite dashboard for monitoring alerts, decisions, metrics and training activity.
- **Docker validation:** reproducible containerized execution through the project launcher.

## 2. Main objective

The project aims to automate and optimize security-alert triage while preserving a human-review path for uncertain or high-risk cases.

```text
Security Alert
     |
     v
Data ingestion / validation
     |
     v
Cleaning + normalization + feature engineering
     |
     v
State representation
     |
     v
Gymnasium RL environment
     |
     +-----------------------------+
     |                             |
     v                             v
Reward model                  RL policy / Q-network
     |                             |
     +-------------+---------------+
                   |
                   v
           Triage decision
      +--------+--------+--------+
      |                 |        |
    allow             block  human_review
      |                 |        |
      +--------+--------+--------+
                   |
                   v
             SOAR / analyst
                   |
                   v
        monitoring + evaluation
```

## 3. Dataset

### 3.1 Dataset family

The project uses the **Microsoft Security Operations Center (Microsoft SOC) alert dataset** as the main historical security-event source.

The repository processes separate training and test CSV files. The preprocessing metadata records the original source columns and the final exported columns used by the RL pipeline.

### 3.2 Source and processed data

The repository records:

- Training source: `Train.csv`
- Test source: `Test.csv`
- Processing chunk size: `50,000` rows
- Training rows after processing: **4,365,976**
- Test rows after processing: **2,413,715**
- Category mappings fitted on **training data only**
- Feature scaler fitted on **training data only**
- Unseen test categories mapped to `-1`

### 3.3 Input fields

The source data contains fields including:

```text
IncidentId
AlertId
Timestamp
Category
MitreTechniques
IncidentGrade
ActionGrouped
ActionGranular
EntityType
EvidenceRole
ThreatFamily
OSFamily
SuspicionLevel
```

The preprocessing stage additionally derives:

```text
hour
day
month
is_weekend
```

The RL observation uses:

```text
Category
MitreTechniques
EntityType
EvidenceRole
ThreatFamily
OSFamily
SuspicionLevel
hour
day
month
is_weekend
```

`IncidentGrade` is used as the historical outcome signal for reward construction and evaluation rather than being passed directly as an observation feature.

## 4. Data preparation pipeline

```text
Raw Microsoft SOC Train/Test CSVs
            |
            v
        Chunked loading
            |
            v
        Data cleaning
            |
            v
        Normalization
            |
            v
      Feature engineering
            |
            +--> hour
            +--> day
            +--> month
            +--> is_weekend
            |
            v
   Categorical encoding / mappings
            |
            v
        Validation
            |
            v
    train_processed.csv
    test_processed.csv
            |
            v
      RL state construction
```

Mapping and scaling are fitted on the training partition only, so test information is not used to fit preprocessing parameters.

## 5. Reinforcement-learning formulation

- **State:** encoded alert/context features derived from the SOC dataset.
- **Action:** operational triage decision from the project action space.
- **Reward:** historical/counterfactual utility derived from the alert outcome and the project reward model.
- **Policy:** learned mapping from alert state to an action.
- **Evaluation:** reward-based and policy-quality metrics on validation and an unseen test holdout.

The current implementation uses a **one-step contextual** formulation. Each alert is treated as a decision point and evaluated against its corresponding reward signal.

## 6. Algorithms

### 6.1 Double DQN — current selected model

**Double Deep Q-Network (Double DQN)** is the current selected algorithm and the main reproducible training/evaluation path.

The recorded model-selection configuration includes:

```text
learning rate : 0.001
gamma         : 0.95
batch size    : 2048
chunk size    : 100000
actual epochs : 80
best epoch    : 60
```

The model-selection rule is:

```text
0.70 * validation_policy_optimality
+ 0.30 * validation_reward_efficiency
```

The unseen test set is not used for model selection.

### 6.2 CQL — second project algorithm

**Conservative Q-Learning (CQL)** is the second offline-RL algorithm in the project. It is included as an alternative conservative value-learning method for the same alert-triage setting.

The README intentionally documents only **Double DQN and CQL** as the project's algorithm set.

## 7. Model selection and evaluation

```text
Train set
   |
   +--> training
   |
   +--> validation
           |
           v
      model selection
           |
           v
      selected model
           |
           v
   Unseen incident-level test set
           |
           v
      final evaluation
```

The current model-comparison artifact records Double DQN as the selected model and explicitly indicates that the test set was not used for selection.

Representative recorded test metrics are:

```text
Average reward       : 0.962962
Oracle average reward: 1.736567
Reward efficiency    : 0.554520
Policy optimality    : 0.768723
```

## 8. Metrics

The project exposes:

- average reward
- oracle average reward
- reward efficiency
- policy optimality
- reward regret
- action distribution
- per-class reward and optimality
- validation score
- throughput and evaluation time

## 9. Application architecture

```text
                         +----------------------+
                         |   React / Vite UI    |
                         | alerts / metrics /   |
                         | decisions / training |
                         +----------+-----------+
                                    |
                                    v
                         +----------------------+
                         |     FastAPI API      |
                         | services + routers   |
                         +----------+-----------+
                                    |
              +---------------------+---------------------+
              |                     |                     |
              v                     v                     v
      +---------------+     +---------------+     +---------------+
      | Data Pipeline |     | RL / Reward   |     | Live Services |
      | preprocess    |     | env + policy  |     | alerts/cycles |
      +-------+-------+     +-------+-------+     +-------+-------+
              |                     |                     |
              +---------------------+---------------------+
                                    |
                                    v
                            +---------------+
                            |    MongoDB    |
                            | operational   |
                            | state/data    |
                            +---------------+
```

## 10. Submission structure

The mandatory academic submission structure is **outside** this application repository. The complete application remains under `rl_project/`.

```text
DS-G07_MD3SI/
├── README.md                 # Professor-facing reproduction instructions
├── requirements.txt          # Submission-level requirements, if needed
├── run_all.sh                # One-command submission launcher
├── configs/                  # External YAML configuration, when required
├── rl_project/               # This complete repository
│   ├── README.md
│   ├── requirements.txt
│   ├── run_all.sh
│   ├── backend/
│   ├── frontend/
│   ├── models/
│   ├── data/
│   ├── docs/
│   └── docker/
├── results/                  # CSV evaluation/training results
├── logs/                     # TensorBoard / run logs
├── figures/                  # PDF figures for the report
├── videos/                   # Agent execution videos, if supplied
├── notebook.md               # Weekly lab/research log
└── report.pdf                # Final report
```

## 11. Professor-facing one-command execution

The **outer** `DS-G07_MD3SI/run_all.sh` should delegate to the tested launcher inside the repository.

```bash
#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

chmod +x "rl_project/run_all.sh"
exec "./rl_project/run_all.sh"
```

The professor therefore executes only:

```bash
./run_all.sh
```

from `DS-G07_MD3SI/`. The wrapper enters `rl_project/run_all.sh`, which performs the real Docker validation.

## 12. Docker execution — recommended method

**Docker is the recommended and reproducible execution path.** It builds and starts:

- MongoDB
- FastAPI backend
- React/Vite frontend served by Nginx

From inside the repository:

```bash
./run_all.sh
```

From the academic submission root:

```bash
./run_all.sh
```

The outer command delegates to `rl_project/run_all.sh`.

The launcher builds a CPU-only backend validation image, builds the frontend, starts the Compose services, waits for backend/frontend readiness, and opens the frontend when `xdg-open` is available.

Typical endpoints are:

```text
Backend : http://127.0.0.1:8000/
Frontend: http://127.0.0.1:8081/
```

The launcher resolves the published frontend/backend ports from Docker Compose instead of assuming a fixed host mapping.

## 13. What `rl_project/run_all.sh` validates

```text
run_all.sh
   |
   +--> verify Docker / Docker Compose
   |
   +--> create temporary CPU-only backend build
   |
   +--> create temporary frontend TypeScript validation build
   |
   +--> build backend
   +--> build frontend
   +--> start MongoDB
   +--> start backend
   +--> start frontend
   |
   +--> wait for backend HTTP readiness
   +--> wait for frontend HTTP readiness
   |
   +--> display running containers
   +--> open frontend
```

The temporary build overrides allow CPU-only validation and frontend type compatibility checks without rewriting the permanent project dependency files/source code.

## 14. Local execution without Docker

Docker is recommended for reproduction. A non-container path is available when Python, Node.js, MongoDB and project dependencies are installed locally.

Typical entry points are:

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000

cd frontend
npm ci
npm run build
```

For grading and reproduction, prefer Docker because it starts all required services together in a controlled environment.

## 15. Important artifacts

Examples of stored project artifacts include:

```text
models/model_comparison.json
models/training_metrics.json
models/real_test_metrics.json
backend/models/real_dqn_agent.pt
```

The repository also contains processed-data metadata describing the train/test transformation and feature contract.

## 16. Reproducibility and research limitations

The reproducible algorithm set documented here is limited to **Double DQN and CQL**.

- Double DQN is the current selected model.
- CQL is the second implemented offline-RL algorithm.
- The test holdout is kept separate from model selection.
- The contextual formulation treats each alert as a one-step decision.

These constraints are documented so that the experiments remain faithful to the available data.

## 17. Team structure

The project was developed collaboratively across:

- RL agent
- data pipeline
- environment
- reward system
- backend API
- database and monitoring
- frontend

Relevant documentation is available in `docs/` and `backend/app/rl_agent/README.md`.

## 18. Quick reproduction checklist

```text
1. Obtain the DS-G07_MD3SI submission package.
2. Run ./run_all.sh from the submission root.
3. The wrapper delegates to rl_project/run_all.sh.
4. Docker builds the CPU-only backend and frontend.
5. MongoDB, backend and frontend start together.
6. Readiness checks validate the running services.
7. Open the displayed frontend URL.
8. Inspect the dashboard, metrics, training/evaluation pages and model artifacts.
```
