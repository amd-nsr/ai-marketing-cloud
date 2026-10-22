import { z } from "zod";

/** Matches the backend's uniform error envelope (apps/core/exceptions.py). */
export const apiErrorEnvelopeSchema = z.object({
  error: z.object({
    code: z.string(),
    message: z.string(),
    details: z.unknown().nullable(),
    request_id: z.string(),
  }),
});

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
    readonly details: unknown = null,
    readonly requestId: string | null = null,
  ) {
    super(message);
    this.name = "ApiError";
  }

  get isUnauthenticated(): boolean {
    return this.code === "not_authenticated" || this.code === "authentication_failed";
  }

  /** Field errors from a validation_error envelope, flattened to first message per field. */
  get fieldErrors(): Record<string, string> {
    if (this.code !== "validation_error" || !this.details || typeof this.details !== "object") {
      return {};
    }
    const out: Record<string, string> = {};
    for (const [field, value] of Object.entries(this.details as Record<string, unknown>)) {
      const first = Array.isArray(value) ? value[0] : value;
      if (typeof first === "string") out[field] = first;
    }
    return out;
  }
}

/** A user-presentable message for any thrown value. */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    const fields = error.fieldErrors;
    const nonField = fields.non_field_errors ?? fields.detail;
    return nonField ?? error.message;
  }
  return "Something went wrong. Please try again.";
}
