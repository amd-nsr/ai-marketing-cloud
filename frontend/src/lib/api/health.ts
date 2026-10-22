import { z } from "zod";

import { apiRequest } from "./client";

const checkSchema = z.object({
  ok: z.boolean(),
  latency_ms: z.number(),
  error: z.string().nullable(),
});

export const readinessSchema = z.object({
  status: z.enum(["ok", "unavailable"]),
  checks: z.record(z.string(), checkSchema),
});

export type Readiness = z.infer<typeof readinessSchema>;

export function getReadiness(init?: RequestInit): Promise<Readiness> {
  return apiRequest("/api/v1/health/ready/", {
    ...init,
    schema: readinessSchema,
    acceptStatuses: [503],
    cache: "no-store",
  });
}
