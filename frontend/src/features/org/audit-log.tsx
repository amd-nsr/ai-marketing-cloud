"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";
import { PageLoading } from "@/components/ui/spinner";
import { useOrg } from "@/hooks/use-org";
import { errorMessage } from "@/lib/api/errors";
import { listAuditEvents } from "@/lib/api/organizations";
import { formatDateTime } from "@/lib/format";

export function AuditLog() {
  const { organization } = useOrg();
  const [page, setPage] = useState(1);
  const events = useQuery({
    queryKey: ["orgs", organization.id, "audit", page],
    queryFn: () => listAuditEvents(organization.id, page),
  });

  return (
    <>
      <PageHeader
        title="Audit log"
        description="Security- and business-relevant actions in this organization."
      />
      {events.isPending && <PageLoading />}
      {events.isError && <Alert tone="danger">{errorMessage(events.error)}</Alert>}
      {events.data && events.data.results.length === 0 && <EmptyState title="No events yet" />}
      {events.data && events.data.results.length > 0 && (
        <Card className="p-0 sm:p-0">
          <ul className="divide-y divide-border">
            {events.data.results.map((e) => (
              <li key={e.id} className="flex flex-wrap items-start justify-between gap-2 px-5 py-3">
                <div className="min-w-0">
                  <p className="font-mono text-sm">{e.action}</p>
                  <p className="text-xs text-muted">
                    {e.actor_type === "system" ? (
                      <Badge tone="info">System</Badge>
                    ) : (
                      (e.actor_email ?? "Unknown user")
                    )}
                    {e.target_type && ` · ${e.target_type}`}
                  </p>
                </div>
                <time className="text-xs text-muted" dateTime={e.created_at}>
                  {formatDateTime(e.created_at)}
                </time>
              </li>
            ))}
          </ul>
          <div className="flex items-center justify-between border-t border-border px-5 py-3">
            <Button
              variant="secondary"
              size="sm"
              disabled={!events.data.previous}
              onClick={() => setPage((p) => p - 1)}
            >
              Previous
            </Button>
            <span className="text-xs text-muted">Page {page}</span>
            <Button
              variant="secondary"
              size="sm"
              disabled={!events.data.next}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </Button>
          </div>
        </Card>
      )}
    </>
  );
}
