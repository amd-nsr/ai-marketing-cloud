"use client";

import { useQuery } from "@tanstack/react-query";

import { getMe } from "@/lib/api/auth";
import { ApiError } from "@/lib/api/errors";

export const ME_QUERY_KEY = ["me"] as const;

/** The signed-in user and their memberships. `data === null` means signed out. */
export function useMe() {
  return useQuery({
    queryKey: ME_QUERY_KEY,
    queryFn: async () => {
      try {
        return await getMe();
      } catch (error) {
        if (error instanceof ApiError && (error.status === 401 || error.status === 403))
          return null;
        throw error;
      }
    },
    staleTime: 60_000,
  });
}
