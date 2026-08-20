import { apiRequest } from "./api";
import type { ApiComponent, AgentStatus } from "../types/domain";

export const systemService = {
  getApis: () => apiRequest<{ components: ApiComponent[] }>("/api/system/apis"),
  getAgentStatus: () => apiRequest<AgentStatus>("/api/agent/status"),
};
