import { qs, request } from "@/lib/api-client";
import type { UpdateBudgetResponse, UsageResponse } from "@/lib/types/api";

export const usage = {
  getStats: (period?: string) =>
    request<UsageResponse>(`/usage?${qs({ period })}`),

  updateBudget: (amount: number) =>
    request<UpdateBudgetResponse>("/usage/budget", {
      method: "PATCH",
      body: JSON.stringify({ monthly_budget_usd: amount }),
    }),
};
