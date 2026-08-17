import { apiRequest } from "./api";
import type { PipelineStats, PipelineStatus } from "../types/domain";

export const pipelineService = {
  getStatus: () => apiRequest<PipelineStatus>("/api/pipeline/status"),
  getStatistics: () => apiRequest<PipelineStats>("/api/pipeline/statistics"),
};
