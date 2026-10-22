import { describe, expect, it, vi } from "vitest";
import { z } from "zod";

import { apiRequest } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";

function mockFetch(status: number, body: unknown) {
  const fetchMock = vi.fn().mockImplementation(
    async () =>
      new Response(JSON.stringify(body), {
        status,
        headers: { "Content-Type": "application/json" },
      }),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

const schema = z.object({ status: z.string() });

describe("apiRequest", () => {
  it("returns schema-validated data on success", async () => {
    const fetchMock = mockFetch(200, { status: "ok" });
    await expect(apiRequest("/api/v1/x/", { schema })).resolves.toEqual({ status: "ok" });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/x/",
      expect.objectContaining({ credentials: "same-origin" }),
    );
  });

  it("maps the backend error envelope to ApiError", async () => {
    mockFetch(404, {
      error: { code: "not_found", message: "Not found.", details: null, request_id: "abc" },
    });
    const error = await apiRequest("/api/v1/x/", { schema }).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 404, code: "not_found", requestId: "abc" });
  });

  it("rejects responses that do not match the schema", async () => {
    mockFetch(200, { unexpected: true });
    await expect(apiRequest("/api/v1/x/", { schema })).rejects.toMatchObject({
      code: "invalid_response",
    });
  });

  it("parses accepted non-2xx statuses as normal responses", async () => {
    mockFetch(503, { status: "unavailable" });
    await expect(apiRequest("/api/v1/x/", { schema, acceptStatuses: [503] })).resolves.toEqual({
      status: "unavailable",
    });
  });

  it("reports network failures distinctly", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(apiRequest("/api/v1/x/", { schema })).rejects.toMatchObject({
      status: 0,
      code: "network_error",
    });
  });

  it("serialises JSON bodies and sends the CSRF cookie as a header", async () => {
    document.cookie = "csrftoken=tok-123";
    const fetchMock = mockFetch(200, { status: "ok" });
    await apiRequest("/api/v1/x/", { schema, method: "POST", body: { a: 1 } });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(init.body).toBe('{"a":1}');
    expect(init.headers).toMatchObject({
      "Content-Type": "application/json",
      "X-CSRFToken": "tok-123",
    });
    document.cookie = "csrftoken=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
  });

  it("fetches a CSRF cookie first when none exists", async () => {
    const fetchMock = mockFetch(200, { status: "ok" });
    await apiRequest("/api/v1/x/", { schema, method: "POST", body: {} });
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/auth/csrf/");
    expect(fetchMock.mock.calls[1][0]).toBe("/api/v1/x/");
  });

  it("does not attach CSRF headers to safe requests", async () => {
    document.cookie = "csrftoken=tok-123";
    const fetchMock = mockFetch(200, { status: "ok" });
    await apiRequest("/api/v1/x/", { schema });
    expect((fetchMock.mock.calls[0][1] as RequestInit).headers).not.toHaveProperty("X-CSRFToken");
    document.cookie = "csrftoken=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
  });

  it("exposes backend field errors", async () => {
    mockFetch(400, {
      error: {
        code: "validation_error",
        message: "The request contains invalid data.",
        details: { email: ["Already taken."] },
        request_id: "r",
      },
    });
    const error = (await apiRequest("/api/v1/x/", { schema }).catch((e: unknown) => e)) as ApiError;
    expect(error.fieldErrors).toEqual({ email: "Already taken." });
  });
});
