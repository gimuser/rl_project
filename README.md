# DS-G02_MD3SI

Professor-facing academic submission for the SOAR-RL-Agent project.

## Project structure

The repository root is the academic submission root (`DS-G02_MD3SI`). The complete application is preserved under `rl_project/`.

```text
DS-G02_MD3SI/
├── README.md
├── requirements.txt
├── run_all.sh
├── configs/
├── rl_project/
│   ├── README.md
│   ├── requirements.txt
│   ├── run_all.sh
│   ├── backend/
│   ├── frontend/
│   ├── models/
│   ├── data/
│   ├── docs/
│   └── docker/
├── results/
├── logs/
├── figures/
├── videos/
├── notebook.md
└── report.pdf
```

## Reproduction / execution

The **only command required from the professor-facing submission root** is:

```bash
./run_all.sh
```

The launcher is intentionally a thin submission wrapper. It does not duplicate or restructure the application. It changes only the entry point so that the professor can execute the complete project from the academic submission root:

```text
DS-G02_MD3SI/run_all.sh
        |
        v
DS-G02_MD3SI/rl_project/run_all.sh
        |
        +--> Docker Compose
        |      +--> MongoDB
        |      +--> FastAPI backend
        |      +--> React/Vite frontend
        |
        +--> CPU-only backend validation image
        +--> frontend build
        +--> readiness checks
        +--> browser launch when xdg-open is available
```

### Requirements

Before execution, the machine must have:

- Docker installed and running
- Docker Compose available through `docker compose`
- `curl` for readiness checks
- `xdg-open` is optional; if unavailable, the frontend URL is printed for manual opening

Then:

```bash
cd DS-G02_MD3SI
chmod +x run_all.sh
./run_all.sh
```

The internal application paths remain under `rl_project/`; application/API routes are not changed by the submission wrapper.

## Dataset

The original large training/evaluation CSV files are intentionally **not committed to GitHub**. They must be supplied separately and placed under:

```text
rl_project/data/
├── processed/
│   ├── train_processed.csv
│   └── test_processed.csv
└── rl_incident/
    ├── train_incident.csv
    └── test_incident.csv
```

This keeps the GitHub submission lightweight while preserving the original project data layout used by the application.

## Results

The root `results/` directory contains copies of the JSON experiment, evaluation, training, preprocessing, inference, and state-quality artifacts produced by the project. These files are provided for inspection without changing the application's original artifact locations under `rl_project/models/`.

When the project is executed, runtime/service output is shown in the terminal and Docker Compose logs can be inspected with:

```bash
cd rl_project
docker compose ps
docker compose logs --tail=100
```

The principal JSON evaluation/training artifacts available in the submission include files such as:

```text
results/real_test_metrics.json
results/training_metrics.json
results/model_comparison.json
results/training_run.json
results/live_inference.json
results/state_quality_v2_summary.json
```

## Application

SOAR-RL-Agent is a reinforcement-learning system for autonomous security-alert triage and analyst workload optimization in a SOAR-oriented pipeline. It combines the data pipeline, Gymnasium-compatible RL environment, reward modeling, offline RL, FastAPI backend, MongoDB persistence, and React/Vite dashboard.

## Technical documentation

The complete technical documentation and application README are located in `rl_project/README.md`.
