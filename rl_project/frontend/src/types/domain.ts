export type ApiHealth = "online" | "offline" | "unknown";

export interface Alert {
  id: string | number;
  title: string;
  severity: string;
  source: string;
}

export interface LiveAlert {
  alert_id: string;
  incident_id: string | number;
  timestamp: string;
  status: string;
  severity: string | number | null;
  title: string;
  source: Record<string, unknown>;
  processed: Record<string, unknown>;
  lineage: Record<string, unknown>;
  assigned_analyst?: string | null;
  agent: {
    status: string;
    action: string;
    confidence: number | null;
    q_values: Record<string, number> | null;
    model_version: string | null;
    requires_human_review: boolean;
  };
  last_human_decision?: {
    analyst_id: string;
    decision: string;
    comment: string;
    action?: string | null;
    timestamp: string;
  } | null;
}

export interface LiveAgentStatus {
  status: string;
  mode: string;
  training: boolean;
  training_status: string;
  model_status: string;
  algorithm: string;
  model_version: string | null;
  policy_metrics: Record<string, unknown> | null;
  total_alerts: number;
  agent_decisions: number;
  human_review_pending: number;
  confidence: number | null;
  environment_health: string;
  note: string;
}

export interface AnalystLoadItem {
  analyst_id: string;
  name: string;
  role: string;
  capacity: number;
  load: number;
  available: number;
  utilization: number;
  active: boolean;
}

export interface AnalystWorkload {
  items: AnalystLoadItem[];
  average_analyst_load: number;
  load_variance: number;
  most_loaded_analyst: AnalystLoadItem | null;
  least_loaded_analyst: AnalystLoadItem | null;
}

export interface SystemLiveStatus {
  api: string;
  database: string;
  live_alerts: number;
  pending_human_review: number;
}

export interface Decision {
  id: number;
  incident_id: number;
  action: string;
  timestamp: string;
}

export interface Reward {
  id: number;
  decision_id: number;
  reward_value: number;
  metrics: Record<string, unknown>;
  timestamp: string;
}

export interface DashboardSummary {
  total_alerts: number | null;
  processed_alerts: number | null;
  total_decisions: number | null;
  total_rewards: number | null;
  average_reward: number | null;
  average_latency: number | null;
  accuracy: number | null;
  database_status: string;
  training_status: string;
  current_episode: number | null;
}

export interface SystemHealth {
  status: string;
}

export interface ApiComponent {
  name: string;
  prefix: string;
  status: string;
  last_seen?: number | null;
  request_count?: number;
}

export interface TrainingStatus {
  status: string;
  current_epoch: number;
}

export interface ExperimentStatus {
  run_id?: string;
  status?: string;
  current_model?: string;
  model_index?: number;
  total_models?: number;
  training?: Record<string, unknown>;
  evaluation?: Record<string, unknown>;
  checkpoint?: string;
  best?: Record<string, unknown>;
}

export interface TrainingHistoryPoint {
  epoch: number;
  loss: number;
}

export interface TrainingHistory {
  history: TrainingHistoryPoint[];
}

export type TrainingCheckpoint = {
  name: string;
  path: string;
};

export interface TrainingCheckpoints {
  checkpoints: TrainingCheckpoint[];
}

export interface PipelineStats {
  total_rows: number;
  total_columns: number;
  missing_values: number;
}

export interface PipelineStatus {
  status: string;
  last_run: string | null;
}

export interface DatabaseHealth {
  status: string;
  database: string;
}

export interface DatabaseStatistics {
  collections_count: number;
  total_objects: number;
}

export interface RewardStatistics {
  mean_reward: number | null;
  max_reward: number | null;
  min_reward: number | null;
}

export interface ToastMessage {
  id: number;
  tone: "success" | "error" | "info";
  title: string;
  description?: string;
}

export interface AgentStatus {
  status: string;
  model_path?: string;
  observation_columns?: string[];
  action_space?: Record<string, string>;
}
