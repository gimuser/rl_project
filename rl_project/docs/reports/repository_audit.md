# Repository audit — 2026-08-11

## Current architecture

The repository contains a FastAPI backend, a React/Vite frontend, MongoDB
repositories, processed Microsoft Defender incident datasets, a DQN/PPO code
base, reward modules, Docker Compose, and shell helpers.  The active runtime
path is FastAPI → MongoDB collections and React → `/api/*`; it was not wired to
the data pipeline or a trained model.

## What works

- `data/processed/train_processed.csv` and `test_processed.csv` exist and are
  readable (401,326 and 147,781 rows respectively; 17 columns; no missing or
  duplicate rows within either split).
- FastAPI routes import and the pre-existing backend test suite completes.
- Compose syntax is valid and the frontend already has loading, error, and
  empty-state primitives.

## Critical findings and priority fixes

1. **P1 data/RL:** production `agent_service` chose a random action;
   `SimpleEnv` generated random observations and rewards; training persisted
   `random.random()` loss values. None can be used in an operational flow.
2. **P1 data contract:** the original preprocessing fits encoders separately
   on train and test, and fits `MinMaxScaler` on their concatenation. It also
   exposes `ActionGrouped` and `ActionGranular`, which are post-triage fields
   and potential leakage. Existing processed CSV files will be retained; a
   runtime compatibility adapter will use a train-only feature contract.
3. **P2 API/database:** alert, decision, and reward routes were disconnected
   CRUD calls. They did not construct state, load a model, execute a safe
   action boundary, record an outcome, or calculate a deterministic reward.
   Dashboard fallbacks reported zeroes/healthy-style values instead of an
   unavailable state.
4. **P2 integrations:** no SIEM, SOAR, Shuffle, TheHive, or Cortex client or
   health status existed. The UI must report configuration/health, never a
   fabricated success.
5. **P3 frontend:** most data views use real API calls, but agent/model,
   integration, outcome, and performance data were absent. Some pages already
   label unavailable fields correctly; these will be connected to real routes.
6. **P0 deployment:** `backend/requirements.txt` omitted packages imported by
   the data/RL runtime (`pandas`, `numpy`, `gymnasium`, and `torch`), so a clean
   Docker build cannot reliably run the application. Compose has no health
   checks and the root environment example is absent.

## Dataset and leakage assessment

The processed splits share the following schema:

`IncidentId`, `Timestamp`, `Category`, `MitreTechniques`, `IncidentGrade`,
`ActionGrouped`, `ActionGranular`, `EntityType`, `EvidenceRole`,
`ThreatFamily`, `OSFamily`, `SuspicionLevel`, `LastVerdict`, `hour`, `day`,
`month`, `is_weekend`.

`IncidentGrade` is the target (train distribution: 0=165,872, 1=76,967,
2=155,740, 3=2,747; test: 0=58,390, 1=27,711, 2=60,555, 3=1,125).  The legacy
pipeline's independent categorical encoders make raw test feature IDs
incompatible with train IDs, and its combined-split scaler leaks test
distribution.  The repair deliberately does **not** overwrite the CSVs. It
defines feature-schema version 2 and transforms only at runtime with mappings
fit on the processed training contract; action columns, target, and incident
identifier are excluded from observations.

## Duplicated/unlinked or fabricated code

- `feature_environment/` duplicates environment concepts but is not imported
  by the running backend.
- `simulation/` is not in the application flow and must remain test/research
  only.
- `dataset_service` returned hard-coded row/column counts.
- `get_dashboard_summary_from_db` contained hard-coded latency, accuracy,
  database, and episode values.
- `trainer.DummyAgent`, `agent_service`, `SimpleEnv`, and training-service
  fallbacks fabricate policy, observations, reward/loss, or outcomes.

## Validation baseline

`PYTHONPATH=backend ./.venv/bin/python -m pytest backend/app/tests -q`
passed 11 legacy tests. Their passing state is not evidence of end-to-end
validity because they assert several of the fabricated routes above; the test
suite will be replaced/extended with isolated tests for the real contract.
