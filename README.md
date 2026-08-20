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

## Reproduction

From the `DS-G02_MD3SI` root, run:

```bash
./run_all.sh
```

The submission launcher delegates execution to the tested application launcher:

```text
DS-G02_MD3SI/run_all.sh
        |
        v
rl_project/run_all.sh
        |
        +--> MongoDB
        +--> FastAPI backend
        +--> React/Vite frontend
        +--> CPU-only Docker validation
```

The complete technical documentation and application README are located in `rl_project/README.md`.

## Results

The `results/` directory contains copies of the JSON experiment, evaluation, training, preprocessing, inference, and state-quality artifacts from `rl_project/models/`. The original artifacts remain in `rl_project/models/` so the application continues to use its existing paths.

## Application

SOAR-RL-Agent is a reinforcement-learning system for autonomous security-alert triage and analyst workload optimization in a SOAR-oriented pipeline. It combines the data pipeline, Gymnasium-compatible RL environment, reward modeling, offline RL, FastAPI backend, MongoDB persistence, and React/Vite dashboard.
