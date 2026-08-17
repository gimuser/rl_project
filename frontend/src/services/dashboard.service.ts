import { apiRequest } from "./api";
import type {
  DashboardSummary,
  DatabaseHealth,
  DatabaseStatistics,
  SystemHealth,
} from "../types/domain";

export const dashboardService = {
  getSummary: () => apiRequest<DashboardSummary>("/api/dashboard/summary"),
  getSystemHealth: () => apiRequest<SystemHealth>("/api/system/health"),
  getDatabaseHealth: () => apiRequest<DatabaseHealth>("/api/database/health"),
  getDatabaseStatistics: () => apiRequest<DatabaseStatistics>("/api/database/statistics"),
};
