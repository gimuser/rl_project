import { apiRequest } from "./api";
import type { Alert } from "../types/domain";

const asQuery = (skip: number, limit: number) => `?skip=${skip}&limit=${limit}`;

export const alertsService = {
  getAlerts: (skip = 0, limit = 100) => apiRequest<Alert[]>(`/api/alerts${asQuery(skip, limit)}`),
  getAlert: (id: string | number) => apiRequest<Alert>(`/api/alerts/${encodeURIComponent(id)}`),
};
