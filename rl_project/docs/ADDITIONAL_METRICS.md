# Additional Metrics — Next Training / Live Run

This measurement plan closes the main evaluation gaps identified by the M122 report and the project cahier des charges. Values must be persisted during the next run. Unavailable values must remain N/A rather than being fabricated.

## Academic RL metrics

| Metric | Calculation | Required output |
|---|---|---|
| Mean final return | Mean return over the last 10 evaluations per seed/run | Per run + aggregate |
| IQM | Interquartile mean across final evaluation returns | rliable aggregate |
| 95% stratified bootstrap CI | Bootstrap CI over matched seed results | Lower/upper CI |
| Per-seed final return | Persist final return for every seed | Seeds 0–4 when executed |
| Steps to threshold | First evaluation reaching a predefined target | Steps/updates/epoch |
| Performance profile | rliable performance profile across configurations/seeds | Figure/table |
| Ablation effect | Matched full system vs. removed/altered enhancement | Effect size + CI |

## Operational SOC metrics

| Metric | Calculation | Data required |
|---|---|---|
| Decision latency | decision_ts − alert_received_ts | Alert + decision timestamps |
| Mean alert processing time | terminal_outcome_ts − alert_received_ts | End-to-end timestamps |
| MTTR / mean response time | first_effective_response_ts − alert_received_ts | Response timestamp |
| Throughput | processed alerts / elapsed seconds | Count + wall time |
| False-positive rate | FP / (FP + TN) | IncidentGrade ground truth + action mapping |
| False-negative rate | FN / (FN + TP) | IncidentGrade ground truth + action mapping |
| Precision | TP / (TP + FP) | Ground truth + action mapping |
| Recall / detection rate | TP / (TP + FN) | Ground truth + action mapping |
| F1-score | 2PR/(P+R) | Precision + recall |
| Human-review rate | human_review alerts / total live alerts | Live decision actions |
| Automation rate | automatically handled alerts / total live alerts | Final outcomes |
| Analyst workload | assigned alerts per analyst + utilization over time | Assignment + workload events |
| Load variance | variance of analyst loads | Analyst workload snapshots |
| Maximum analyst utilization | max utilization across analysts | Analyst workload snapshots |
| Analyst-load reduction | matched baseline load − RL load | Baseline + RL workload |
| Playbook automation rate | automatic playbook executions / eligible actions | Playbook execution log |
| Audit completeness | complete decision records / total decisions | Alert, action, confidence, model, analyst, timestamps |
| System availability | uptime / observation window | Service health events |
| Recovery time | service_ready_ts − failure_ts | Failure/recovery events |
| Scalability | latency/throughput under increasing alert load | Load-test measurements |

## Existing project metrics to retain

- Average reward
- Policy optimality
- Reward efficiency
- Reward regret when available
- Test sample count
- Action distribution
- Training loss history
- Policy reward history
- Validation score history
- Cumulative optimizer updates
- Best epoch / best checkpoint

## Persistence requirements for the next run

The evaluator/live pipeline should persist at least:

1. alert_received_ts
2. processed_ts
3. decision_ts
4. first_effective_response_ts
5. final_action_ts
6. IncidentGrade / ground-truth label
7. model_action
8. final_action
9. confidence
10. model_version and algorithm
11. human_review flag/reason
12. analyst_id and analyst workload snapshots
13. playbook execution outcome where applicable
14. service failure/recovery events
15. seed/run/configuration identifiers for statistical aggregation
16. matched baseline and ablation identifiers where applicable

## Alignment with the cahier des charges

The cahier des charges explicitly targets MTTR reduction, triage quality, analyst-load optimization, real-time decision behavior, dashboard reporting, and decision traceability. It also specifies a target decision latency below 500 ms per alert, scalability toward 10,000 alerts/day, and recovery time below 2 minutes.

These operational targets must be reported separately from the offline RL reward metrics so that learning quality and operational effectiveness are not conflated.
