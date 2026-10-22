import type { z } from "zod";

import { ApiError, apiErrorEnvelopeSchema } from "./errors";

export interface ApiRequestOptions<T extends z.ZodType> extends Omit<RequestInit, "body"> {
  /** Validates the response body; the result is typed from the schema. */
  schema: T;
  /** Serialised as JSON, or sent as-is when it is FormData. */
  body?: unknown;
  /**
   * Statuses whose body is still a valid, schema-shaped response
   * (e.g. readiness returns 503 with a normal body).
   */
  acceptStatuses?: number[];
}

const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);
const CSRF_COOKIE = "csrftoken";

/**
 * Browser-side requests use relative URLs, which Next.js proxies to Django.
 * Server-side requests must call Django directly via BACKEND_INTERNAL_URL.
 */
function resolveUrl(path: string): string {
  if (typeof window !== "undefined") return path;
  const base = process.env.BACKEND_INTERNAL_URL ?? "http://localhost:8000";
  return new URL(path, base).toString();
}

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.split("; ").find((c) => c.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.slice(name.length + 1)) : null;
}

/**
 * Django rotates the CSRF token at login, so it is read from the cookie on every
 * unsafe request rather than cached. If no cookie exists yet, one is requested.
 */
async function csrfToken(): Promise<string | null> {
  const existing = readCookie(CSRF_COOKIE);
  if (existing || typeof window === "undefined") return existing;
  await fetch("/api/v1/auth/csrf/", { credentials: "same-origin" });
  return readCookie(CSRF_COOKIE);
}

export async function apiRequest<T extends z.ZodType>(
  path: string,
  { schema, body, acceptStatuses = [], headers, method = "GET", ...init }: ApiRequestOptions<T>,
): Promise<z.infer<T>> {
  const upperMethod = method.toUpperCase();
  const isForm = typeof FormData !== "undefined" && body instanceof FormData;
  const requestHeaders: Record<string, string> = {
    Accept: "application/json",
    ...(body !== undefined && !isForm ? { "Content-Type": "application/json" } : {}),
    ...(headers as Record<string, string> | undefined),
  };
  if (!SAFE_METHODS.has(upperMethod)) {
    const token = await csrfToken();
    if (token) requestHeaders["X-CSRFToken"] = token;
  }

  let response: Response;
  try {
    response = await fetch(resolveUrl(path), {
      ...init,
      method: upperMethod,
      headers: requestHeaders,
      body: body === undefined ? undefined : isForm ? (body as FormData) : JSON.stringify(body),
      credentials: "same-origin",
    });
  } catch (cause) {
    throw new ApiError("Could not reach the server.", 0, "network_error", String(cause));
  }

  const payload: unknown = response.status === 204 ? null : await response.json().catch(() => null);

  if (!response.ok && !acceptStatuses.includes(response.status)) {
    const envelope = apiErrorEnvelopeSchema.safeParse(payload);
    if (envelope.success) {
      const { code, message, details, request_id } = envelope.data.error;
      throw new ApiError(message, response.status, code, details, request_id);
    }
    throw new ApiError(
      `Request failed with status ${response.status}.`,
      response.status,
      "http_error",
    );
  }

  const parsed = schema.safeParse(payload);
  if (!parsed.success) {
    throw new ApiError(
      "The server returned an unexpected response.",
      response.status,
      "invalid_response",
      parsed.error.issues,
    );
  }
  return parsed.data;
}
