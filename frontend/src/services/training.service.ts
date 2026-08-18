import { apiRequest } from "./api";

export type ValidationMetrics = {
  policy_optimality?: number | null;
  reward_efficiency?: number | null;
};

export type CandidateValidation = {
  policy_optimality?: number | null;
  reward_efficiency?: number | null;
};

export type TrainingModelConfig = {
  name: string;
  learning_rate: number;
  gamma: number;
  batch_size: number;
  hidden_dim: number;
  max_total_updates: number;
  cql_alpha?: number;
  iql_expectile?: number;
  iql_beta?: number;
  bcq_threshold?: number;
};

export type TrainingGlobalConfig = {
  max_epochs: number;
  min_epochs: number;
  patience: number;
  validation_every: number;
  min_delta: number;
  max_total_updates: number;
  chunk_size: number;
  train_ratio: number;
  validation_seed: number;
  seed: number;
  target_update: number;
  metric_sample_rows: number;
  telemetry_window: number;
};

export type RewardConfig = Record<string, Record<string, number>>;

export type ModelCandidate = {
  name?: string | null;
  algorithm?: string | null;
  display_name?: string | null;
  behavior_action_mode?: string | null;
  research_warning?: string | null;
  learning_rate?: number | null;
  actual_epochs?: number | null;
  best_epoch?: number | null;
  validation_score?: number | null;
  stopping_reason?: string | null;
  status?: string | null;
  best_validation?: CandidateValidation | null;
  live_inference?: Record<string, unknown> | null;
  live_cycle_id?: string | null;
};

export type AuthoritativeHistoryPoint = {
  run_id?: string | null;
  algorithm?: string | null;
  epoch: number;
  loss: number;
  avg_reward?: number | null;
  average_reward?: number | null;
  policy_reward?: number | null;
  oracle_average_reward?: number | null;
  reward_efficiency?: number | null;
  updates?: number | null;
  total_updates?: number | null;
  updates_per_epoch?: number | null;
  rows?: number | null;
  incidents?: number | null;
  action_distribution?: Record<string, number> | null;
  time_seconds?: number | null;
  validation?: ValidationMetrics | null;
  validation_score?: number | null;
  patience_used?: number | null;
  best_epoch?: number | null;
  improved?: boolean | null;
  stopping_reason?: string | null;
};

export type AuthoritativeResults = {
  run_id?: string | null;
  source?: string;
  status?: string;
  dataset?: {
    name?: string;
    train_rows?: number | null;
    validation_rows?: number | null;
    test_rows?: number | null;
    train_incidents?: number | null;
    validation_incidents?: number | null;
    test_incidents?: number | null;
    incident_overlap?: number | null;
    feature_count?: number | null;
    synthetic_data?: boolean | null;
    unseen_incidents?: boolean | null;
  };
  training?: {
    run_id?: string | null;
    model_name?: string | null;
    display_name?: string | null;
    algorithm?: string | null;
    behavior_action_mode?: string | null;
    research_warning?: string | null;
    candidate_index?: number | null;
    candidate_count?: number | null;
    selected_models?: string[];
    learning_rate?: number | null;
    gamma?: number | null;
    epochs?: number | null;
    actual_epochs?: number | null;
    min_epochs?: number | null;
    patience?: number | null;
    min_delta?: number | null;
    validation_every?: number | null;
    stability_window?: number | null;
    stability_tolerance?: number | null;
    batch_size?: number | null;
    chunk_size?: number | null;
    hidden_dim?: number | null;
    target_update?: number | null;
    updates_per_epoch?: number | null;
    max_total_updates?: number | null;
    total_updates_used?: number | null;
    final_epoch?: number | null;
    final_loss?: number | null;
    final_avg_reward?: number | null;
    policy_reward?: number | null;
    oracle_average_reward?: number | null;
    reward_efficiency?: number | null;
    action_distribution?: Record<string, number> | null;
    validation?: ValidationMetrics | null;
    validation_score?: number | null;
    patience_used?: number | null;
    best_epoch?: number | null;
    stopping_reason?: string | null;
    history?: AuthoritativeHistoryPoint[];
  };
  comparison?: {
    status?: string;
    selection_rule?: string;
    test_used_for_selection?: boolean;
    candidates?: ModelCandidate[];
    best?: ModelCandidate | null;
  } | null;
  evaluation?: {
    samples?: number | null;
    throughput_rows_per_second?: number | null;
    average_reward?: number | null;
    oracle_average_reward?: number | null;
    policy_optimality?: number | null;
    reward_efficiency?: number | null;
    reward_regret?: number | null;
    action_distribution?: Record<string, number> | null;
    per_class?: Record<string, { rows?: number; average_reward?: number; optimality?: number }> | null;
  };
  model?: {
    path?: string | null;
    exists?: boolean;
    size_bytes?: number | null;
    modified_at?: string | null;
  };
  live_inference?: {
    run_id?: string | null;
    status?: string;
    decision_cycle_id?: string | null;
    cycle_id?: string | null;
    model_version?: string | null;
    human_review_routed?: number | null;
    alerts_processed?: number | null;
    alerts_considered?: number | null;
    action_distribution?: Record<string, number> | null;
    errors?: Array<Record<string, unknown>>;
    summary?: Record<string, unknown> | null;
  } | null;
  post_training?: {
    status?: string;
    model?: Record<string, unknown> | null;
    inference?: Record<string, unknown> | null;
    decision_cycle?: string | null;
    live_inference?: Record<string, unknown> | null;
  } | null;
};

export type AuthoritativeTrainingStatus = {
  status: string;
  message?: string;
  started_at?: string | null;
  pid?: number | null;
  results?: AuthoritativeResults | null;
};

export type TrainingStartPayload = {
  modelNames: string[];
  training: TrainingGlobalConfig;
  modelConfigs: TrainingModelConfig[];
  rewards: RewardConfig;
};

export const getAuthoritativeFullTrainingStatus = () =>
  apiRequest<AuthoritativeTrainingStatus>("/api/training-control");

export const startAuthoritativeFullTraining = (payload: TrainingStartPayload) =>
  apiRequest<{ status: string; message?: string; selected_models?: string[]; run_id?: string }>("/api/training-control", {
    method: "POST",
    body: JSON.stringify({
      model_names: payload.modelNames,
      training: payload.training,
      model_configs: payload.modelConfigs,
      rewards: payload.rewards,
    }),
  });

export const stopAuthoritativeFullTraining = () =>
  apiRequest<{ status: string; message?: string }>("/api/training-control/stop", { method: "POST" });
