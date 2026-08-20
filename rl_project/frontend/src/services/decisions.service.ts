import { apiRequest } from "./api";
import type { Decision } from "../types/domain";

export type LiveDecision = {
  decision_id: string;
  alert_id: string;
  incident_id: string | number | null;
  action: string;
  model_action?: string | null;
  confidence?: number | null;
  action_margin?: number | null;
  uncertainty_reason?: string | null;
  algorithm?: string | null;
  model_version?: string | null;
  status?: string | null;
  assigned_analyst?: string | null;
  source_category?: string | null;
  verdict?: string | null;
  timestamp: string;
};

export type LiveDecisionResponse = {
  items: LiveDecision[];
  total: number;
  cycle_id: string | null;
  summary: {
    considered?: number;
    processed?: number;
    action_distribution?: Record<string, number>;
    human_review?: number;
  };
};

export const decisionsService = {
  // Legacy decisions endpoint retained for compatibility.
  getDecisions: (skip = 0, limit = 100) =>
    apiRequest<Decision[]>(`/api/decisions?skip=${skip}&limit=${limit}`),

  // Authoritative live inference history for the latest 40-alert cycle.
  getLiveDecisions: (limit = 100, cycleId?: string) => {
    const query = new URLSearchParams({ limit: String(limit) });
    if (cycleId) query.set("cycle_id", cycleId);
    return apiRequest<LiveDecisionResponse>(`/api/live-decisions?${query.toString()}`);
  },
};
