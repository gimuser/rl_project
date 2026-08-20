import { apiRequest } from "./api";
import type {
  AnalystWorkload,
  LiveAgentStatus,
  LiveAlert,
  SystemLiveStatus,
} from "../types/domain";

export type LiveActivityItem = {
  alert_id: string;
  actor: string;
  action: string;
  details: Record<string, unknown>;
  timestamp: string;
};

export type AnalystAction = LiveActivityItem;

export const liveAlertsService = {
  getAlerts: (skip = 0, limit = 100, search = "", severity = "all") => {
    const query = new URLSearchParams({ skip: String(skip), limit: String(limit) });
    if (search.trim()) query.set("search", search.trim());
    if (severity !== "all") query.set("severity", severity);
    return apiRequest<{ items: LiveAlert[]; total: number }>(`/api/live-alerts?${query.toString()}`);
  },

  getAlert: (id: string) =>
    apiRequest<LiveAlert & { history?: Record<string, unknown>[] }>(`/api/live-alerts/${encodeURIComponent(id)}`),

  getHistory: (id: string) =>
    apiRequest<{ items: Record<string, unknown>[]; total: number }>(`/api/live-alerts/${encodeURIComponent(id)}/history`),

  getHumanReview: () =>
    apiRequest<{ items: LiveAlert[]; total: number }>("/api/human-review"),

  review: (id: string, payload: { analyst_id: string; decision: string; comment?: string; action?: string }) =>
    apiRequest<LiveAlert>(`/api/live-alerts/${encodeURIComponent(id)}/review`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  assign: (id: string, analyst_id: string) =>
    apiRequest<LiveAlert>(`/api/live-alerts/${encodeURIComponent(id)}/assign`, {
      method: "POST",
      body: JSON.stringify({ analyst_id }),
    }),

  getAgentStatus: () => apiRequest<LiveAgentStatus>("/api/agent/live-status"),

  getWorkload: () => apiRequest<AnalystWorkload>("/api/analysts/live-workload"),

  getSystemStatus: () => apiRequest<SystemLiveStatus>("/api/system/live-status"),

  getActivity: (limit = 100) =>
    apiRequest<{ items: LiveActivityItem[]; total: number }>(`/api/live-activity?limit=${limit}`),

  getPendingForAnalyst: (analystId?: string, limit = 100) => {
    const query = new URLSearchParams({ limit: String(limit) });
    if (analystId) query.set("analyst_id", analystId);
    return apiRequest<{ items: LiveAlert[]; total: number }>(`/api/analysts/pending-alerts?${query.toString()}`);
  },

  getRecentAnalystActions: (analystId?: string, limit = 100) => {
    const query = new URLSearchParams({ limit: String(limit) });
    if (analystId) query.set("analyst_id", analystId);
    return apiRequest<{ items: AnalystAction[]; total: number }>(`/api/analysts/recent-actions?${query.toString()}`);
  },
};
