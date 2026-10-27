import { useQuery } from "@tanstack/react-query";

import { getRequestRouting } from "@/features/dashboard/api";

export function useRequestRouting(requestId: string | null | undefined, enabled = true) {
  return useQuery({
    queryKey: ["dashboard", "request-routing", requestId],
    queryFn: () => getRequestRouting(requestId ?? ""),
    enabled: enabled && Boolean(requestId),
    retry: false,
  });
}
