import { apiRequest } from "./api";

export type AuthoritativeMetrics = {
  status: string;
  training: {
    epochs?: number | null;
    history: Array<{
      epoch: number;
      loss: number;
      average_reward?: number | null;
      updates?: number | null;
      time_seconds?: number | null;
    }>;
    latest_loss?: number | null;
    latest_reward?: number | null;
  };
  evaluation: {
    samples?: number | null;
    average_reward?: number | null;
    throughput_rows_per_second?: number | null;
    policy_optimality?: number | null;
    reward_efficiency?: number | null;
    reward_regret?: number | null;
    action_distribution?: Record<string, number> | null;
    per_class?: Record<string, { rows?: number; average_reward?: number; optimality?: number }> | null;
    accuracy?: number | null;
    precision?: number | null;
    recall?: number | null;
    f1?: number | null;
    mttr?: number | null;
  };
};

export const getAuthoritativeMetrics = () =>
  apiRequest<AuthoritativeMetrics>("/api/authoritative-metrics");
