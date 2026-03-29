import { request } from "@/lib/api-client";
import type { OnboardingRequest, OnboardingResponse } from "@/lib/types/api";

export const onboarding = {
  create: (data: OnboardingRequest) =>
    request<OnboardingResponse>("/onboarding", {
      method: "POST",
      body: JSON.stringify(data),
    }),
};
