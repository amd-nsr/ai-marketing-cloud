"use client";

import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";

import { Alert } from "@/components/ui/alert";
import { Card, CardHeader } from "@/components/ui/card";
import { PageLoading } from "@/components/ui/spinner";
import { errorMessage } from "@/lib/api/errors";
import { getDataDeletionStatus } from "@/lib/api/meta";
import { formatDateTime } from "@/lib/format";

const LABEL = {
  received: "Received, in progress",
  completed: "Completed",
  failed: "Couldn't be completed. Contact support with your confirmation code.",
} as const;

export function DataDeletionStatus() {
  const { code } = useParams<{ code: string }>();
  const status = useQuery({
    queryKey: ["meta-data-deletion", code],
    queryFn: () => getDataDeletionStatus(code),
    retry: false,
  });
  return (
    <Card>
      <CardHeader
        title="Facebook data deletion"
        description="Status of your request to delete the data this app received from Facebook."
      />
      {status.isPending && <PageLoading />}
      {status.isError && <Alert tone="danger">{errorMessage(status.error)}</Alert>}
      {status.data && (
        <dl className="grid gap-3 text-sm">
          <div>
            <dt className="text-xs text-muted">Confirmation code</dt>
            <dd className="font-mono break-all">{status.data.confirmation_code}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted">Status</dt>
            <dd>{LABEL[status.data.status]}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted">Requested</dt>
            <dd>{formatDateTime(status.data.requested_at)}</dd>
          </div>
          {status.data.completed_at && (
            <div>
              <dt className="text-xs text-muted">Finished</dt>
              <dd>{formatDateTime(status.data.completed_at)}</dd>
            </div>
          )}
        </dl>
      )}
    </Card>
  );
}
