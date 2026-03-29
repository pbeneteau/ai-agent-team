/**
 * TanStack Query hooks for Onboarding.
 */

import { useMutation } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { OnboardingRequest } from "@/lib/types/api";

export function useOnboarding() {
  return useMutation({
    mutationFn: (data: OnboardingRequest) => api.onboarding.create(data),
  });
}
