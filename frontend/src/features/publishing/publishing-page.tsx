"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Badge, type BadgeTone } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";
import { PageLoading } from "@/components/ui/spinner";
import { Tabs } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/toast";
import { useOrg } from "@/hooks/use-org";
import { errorMessage } from "@/lib/api/errors";
import {
  cancelJob,
  type JobStatus,
  listJobs,
  type PublishingJob,
  retryJob,
} from "@/lib/api/publishing";
import { formatDateTime } from "@/lib/format";
import { PLATFORM_LABEL } from "@/features/content/labels";

export const JOB_STATUS: Record<JobStatus, { label: string; tone: BadgeTone }> = {
  scheduled: { label: "Scheduled", tone: "info" },
  queued: { label: "Queued", tone: "info" },
  publishing: { label: "Publishing", tone: "info" },
  published: { label: "Published", tone: "success" },
  failed: { label: "Failed", tone: "danger" },
  cancelled: { label: "Cancelled", tone: "neutral" },
  needs_reconciliation: { label: "Checking outcome", tone: "warning" },
};

const UNCONFIRMED = new Set(["unconfirmed", "outcome_unknown", "internal_error"]);

type Tab = "upcoming" | "published" | "problems" | "all";
const FILTER: Record<Tab, string | undefined> = {
  upcoming: "scheduled,queued,publishing,needs_reconciliation",
  published: "published",
  problems: "failed",
  all: undefined,
};

function JobRow({ job, onRetry }: { job: PublishingJob; onRetry: (job: PublishingJob) => void }) {
  const { organization, can } = useOrg();
  const queryClient = useQueryClient();
  const toast = useToast();
  const meta = JOB_STATUS[job.status];
  const publish = can("publishing.publish");

  const cancel = async () => {
    try {
      await cancelJob(organization.id, job.id);
      toast("Cancelled.");
      await queryClient.invalidateQueries({ queryKey: ["orgs", organization.id, "publishing"] });
    } catch (e) {
      toast(errorMessage(e), "danger");
    }
  };

  return (
    <li className="flex flex-col gap-2 rounded-lg border border-border bg-surface p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <Link
            href={`/o/${organization.id}/content/${job.content_item}`}
            className="font-medium hover:underline"
          >
            {job.content_title}
          </Link>
          <p className="text-xs text-muted">
            {PLATFORM_LABEL[job.platform]} · {job.account_name} · version {job.version_number}
            {job.initiated_by === "automation" && " · automated"}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {job.is_mock && <Badge tone="warning">Simulation</Badge>}
          <Badge tone={meta.tone}>{meta.label}</Badge>
        </div>
      </div>
      <p className="text-sm">
        {job.status === "published" && job.published_at && (
          <>Published {formatDateTime(job.published_at)}. </>
        )}
        {job.status === "scheduled" && job.scheduled_for && (
          <>Will publish {formatDateTime(job.scheduled_for)}. </>
        )}
        {job.status === "queued" && job.next_attempt_at && (
          <>Retrying around {formatDateTime(job.next_attempt_at)}. </>
        )}
        {job.error_message && (
          <span className={job.status === "failed" ? "text-danger" : "text-muted"}>
            {job.error_message}
          </span>
        )}
      </p>
      <div className="flex flex-wrap items-center gap-2">
        {job.permalink && (
          <a
            href={job.permalink}
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm text-primary hover:underline"
          >
            View post ↗
          </a>
        )}
        {publish && (job.status === "scheduled" || job.status === "queued") && (
          <Button size="sm" variant="secondary" onClick={cancel}>
            Cancel
          </Button>
        )}
        {publish && job.status === "failed" && job.error_code !== "content_changed" && (
          <Button size="sm" variant="secondary" onClick={() => onRetry(job)}>
            Retry
          </Button>
        )}
        {job.attempt_log.length > 0 && (
          <details className="text-xs text-muted">
            <summary className="cursor-pointer">
              {job.attempts} attempt{job.attempts === 1 ? "" : "s"}
            </summary>
            <ul className="mt-1 flex flex-col gap-0.5">
              {job.attempt_log.map((a) => (
                <li key={a.number}>
                  #{a.number} {formatDateTime(a.started_at)}: {a.outcome.replaceAll("_", " ")}
                  {a.error_message && ` (${a.error_message})`}
                </li>
              ))}
            </ul>
          </details>
        )}
      </div>
    </li>
  );
}

export function PublishingPage() {
  const { organization } = useOrg();
  const queryClient = useQueryClient();
  const toast = useToast();
  const [tab, setTab] = useState<Tab>("upcoming");
  const [retrying, setRetrying] = useState<PublishingJob | null>(null);
  const jobs = useQuery({
    queryKey: ["orgs", organization.id, "publishing", tab],
    queryFn: () => listJobs(organization.id, { status: FILTER[tab] }),
    refetchInterval: tab === "upcoming" ? 5000 : false,
  });

  const retry = async (job: PublishingJob, confirm: boolean) => {
    try {
      await retryJob(organization.id, job.id, confirm);
      toast("Retrying.");
      setRetrying(null);
      await queryClient.invalidateQueries({ queryKey: ["orgs", organization.id, "publishing"] });
    } catch (e) {
      toast(errorMessage(e), "danger");
    }
  };

  return (
    <>
      <PageHeader
        title="Publishing"
        description="Everything scheduled, sent, and published, with every attempt recorded."
      />
      <Tabs
        label="Publishing status"
        value={tab}
        onChange={setTab}
        items={[
          { value: "upcoming", label: "Upcoming" },
          { value: "published", label: "Published" },
          { value: "problems", label: "Failed" },
          { value: "all", label: "All" },
        ]}
      />
      <div className="mt-4">
        {jobs.isPending && <PageLoading />}
        {jobs.isError && <Alert tone="danger">{errorMessage(jobs.error)}</Alert>}
        {jobs.data?.count === 0 && (
          <EmptyState
            title={tab === "upcoming" ? "Nothing scheduled" : "Nothing here yet"}
            description="Approved content can be published or scheduled from the content editor."
          />
        )}
        <ul className="flex flex-col gap-3">
          {jobs.data?.results.map((job) => (
            <JobRow
              key={job.id}
              job={job}
              onRetry={(j) =>
                UNCONFIRMED.has(j.error_code) ? setRetrying(j) : void retry(j, false)
              }
            />
          ))}
        </ul>
      </div>
      <ConfirmDialog
        open={retrying !== null}
        onCancel={() => setRetrying(null)}
        onConfirm={() => retrying && retry(retrying, true)}
        tone="primary"
        title="Check before retrying"
        description="We couldn't confirm whether this post was published. Open the account and make sure it isn't there; retrying could otherwise post it twice."
        confirmLabel="It's not there, retry"
      />
    </>
  );
}
