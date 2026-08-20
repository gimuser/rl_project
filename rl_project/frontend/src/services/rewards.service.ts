import { apiRequest } from "./api";
import type { Reward, RewardStatistics } from "../types/domain";

export const rewardsService = {
  getRewards: (skip = 0, limit = 100) =>
    apiRequest<Reward[]>(`/api/rewards?skip=${skip}&limit=${limit}`),
  getStatistics: () => apiRequest<RewardStatistics>("/api/rewards/statistics"),
};
