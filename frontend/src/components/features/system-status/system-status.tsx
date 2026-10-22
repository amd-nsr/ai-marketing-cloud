"use client";

import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/errors";
import { getReadiness, type Readiness } from "@/lib/api/health";

type State =
  | { kind: "loading" }
  | { kind: "loaded"; data: Readiness; checkedAt: Date }
  | { kind: "error"; message: string };

const CHECK_LABELS: Record<string, string> = { database: "PostgreSQL", redis: "Redis" };

async function fetchStatus(): Promise<State> {
  try {
    const data = await getReadiness();
    return { kind: "loaded", data, checkedAt: new Date() };
  } catch (error) {
    const message =
      error instanceof ApiError ? error.message : "Something went wrong checking the API.";
    return { kind: "error", message };
  }
}

/** Calls the backend readiness endpoint from the browser via the /api proxy. */
export function SystemStatus() {
  const [state, setState] = useState<State>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    void fetchStatus().then((next) => {
      if (!cancelled) setState(next);
    });
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  const refresh = () => {
    setState({ kind: "loading" });
    setAttempt((n) => n + 1);
  };

  return (
    <section
      aria-labelledby="system-status-heading"
      className="rounded-xl border border-border bg-surface p-6"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 id="system-status-heading" className="text-base font-semibold">
            System status
          </h2>
          <p className="text-sm text-muted">Live check of the API and its dependencies.</p>
        </div>
        <Button variant="secondary" onClick={refresh} disabled={state.kind === "loading"}>
          {state.kind === "loading" ? "Checking…" : "Check again"}
        </Button>
      </div>

      <div className="mt-5" aria-live="polite">
        {state.kind === "loading" && <p className="text-sm text-muted">Contacting the API…</p>}

        {state.kind === "error" && (
          <div role="alert" className="rounded-md bg-danger-soft p-3 text-sm text-danger">
            <p className="font-medium">API unreachable</p>
            <p>{state.message}</p>
          </div>
        )}

        {state.kind === "loaded" && (
          <>
            <p className="mb-3 flex items-center gap-2 text-sm">
              API
              <Badge tone={state.data.status === "ok" ? "success" : "danger"}>
                {state.data.status === "ok" ? "Ready" : "Degraded"}
              </Badge>
            </p>
            <ul className="divide-y divide-border rounded-md border border-border">
              {Object.entries(state.data.checks).map(([name, check]) => (
                <li key={name} className="flex items-center justify-between px-3 py-2 text-sm">
                  <span>{CHECK_LABELS[name] ?? name}</span>
                  <span className="flex items-center gap-3">
                    <span className="font-mono text-xs text-muted">{check.latency_ms} ms</span>
                    <Badge tone={check.ok ? "success" : "danger"}>
                      {check.ok ? "Healthy" : `Failing${check.error ? ` (${check.error})` : ""}`}
                    </Badge>
                  </span>
                </li>
              ))}
            </ul>
            <p className="mt-3 text-xs text-muted">
              Checked at {state.checkedAt.toLocaleTimeString()}
            </p>
          </>
        )}
      </div>
    </section>
  );
}
