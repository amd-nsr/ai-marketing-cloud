"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/input";
import { useToast } from "@/components/ui/toast";
import { useOrg } from "@/hooks/use-org";
import {
  approveContent,
  archiveContent,
  cancelApproval,
  type ContentItem,
  deleteContent,
  rejectContent,
  submitContent,
  unarchiveContent,
} from "@/lib/api/content";
import { errorMessage } from "@/lib/api/errors";
import { formatDateTime } from "@/lib/format";
import { cancelJob, listJobs } from "@/lib/api/publishing";
import { PublishDialog } from "@/features/publishing/publish-dialog";
import { JOB_STATUS } from "@/features/publishing/publishing-page";
import { Badge } from "@/components/ui/badge";

import { isSocial, StatusBadge } from "../labels";
import { useItemApprovals, useRefreshItem } from "./queries";

export function WorkflowPanel({ item }: { item: ContentItem }) {
  const { organization, can } = useOrg();
  const router = useRouter();
  const toast = useToast();
  const refresh = useRefreshItem();
  const approvals = useItemApprovals(item.id);
  const [note, setNote] = useState("");
  const [comment, setComment] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const showJobs = ["scheduled", "published", "approved"].includes(item.status);
  const jobs = useQuery({
    queryKey: ["orgs", organization.id, "publishing", "item", item.id],
    queryFn: () => listJobs(organization.id, { content_item: item.id }),
    enabled: showJobs,
    refetchInterval: item.status === "scheduled" ? 4000 : false,
  });
  const latestJob = jobs.data?.results[0];

  const run = (fn: () => Promise<unknown>, success: string) => async () => {
    try {
      await fn();
      await refresh();
      setNote("");
      setComment("");
      toast(success);
    } catch (e) {
      toast(errorMessage(e), "danger");
    }
  };

  const remove = useMutation({
    mutationFn: () => deleteContent(organization.id, item.id),
    onSuccess: async () => {
      await refresh();
      toast("Content deleted.");
      router.replace(`/o/${organization.id}/content`);
    },
    onError: (e) => toast(errorMessage(e), "danger"),
  });

  const history = approvals.data?.results ?? [];
  const pending = history.find((a) => a.status === "pending");
  const lastDecision = history.find((a) => a.status === "rejected" || a.status === "approved");
  const blocking = (item.current_version?.checks ?? []).filter((c) => c.severity === "error");

  return (
    <Card>
      <CardHeader title="Status" actions={<StatusBadge status={item.status} />} />
      <div className="flex flex-col gap-3 text-sm">
        {(item.status === "draft" || item.status === "changes_requested") && (
          <>
            {item.status === "changes_requested" && lastDecision?.comment && (
              <Alert
                tone="warning"
                title={`Changes requested by ${lastDecision.decided_by_email ?? "a reviewer"}`}
              >
                {lastDecision.comment}
              </Alert>
            )}
            {can("content.submit") ? (
              <>
                {blocking.length > 0 && (
                  <p className="text-xs text-danger">Fix the issues below before submitting.</p>
                )}
                <Textarea
                  aria-label="Note for the reviewer"
                  placeholder="Note for the reviewer (optional)"
                  rows={2}
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                />
                <Button
                  disabled={blocking.length > 0 || !item.current_version}
                  onClick={run(
                    () => submitContent(organization.id, item.id, note),
                    "Submitted for approval.",
                  )}
                >
                  Submit for approval
                </Button>
              </>
            ) : (
              <p className="text-muted">An editor or admin can submit this for approval.</p>
            )}
          </>
        )}

        {item.status === "in_review" && pending && (
          <>
            <p>
              Submitted by {pending.requested_by_email ?? "a teammate"} on{" "}
              {formatDateTime(pending.created_at)} (version {pending.version.number}).
            </p>
            {pending.request_note && (
              <p className="rounded bg-neutral-soft p-2 text-muted">“{pending.request_note}”</p>
            )}
            {can("content.approve") ? (
              <>
                <Textarea
                  aria-label="Review comment"
                  placeholder="Comment (required to request changes)"
                  rows={2}
                  value={comment}
                  onChange={(e) => setComment(e.target.value)}
                />
                <div className="flex flex-wrap gap-2">
                  <Button
                    onClick={run(
                      () => approveContent(organization.id, pending.id, comment),
                      "Approved.",
                    )}
                  >
                    Approve
                  </Button>
                  <Button
                    variant="secondary"
                    disabled={!comment.trim()}
                    onClick={run(
                      () => rejectContent(organization.id, pending.id, comment),
                      "Changes requested.",
                    )}
                  >
                    Request changes
                  </Button>
                </div>
              </>
            ) : (
              <p className="text-muted">Waiting for an owner or admin to review.</p>
            )}
            {can("content.submit") && (
              <Button
                variant="ghost"
                size="sm"
                onClick={run(
                  () => cancelApproval(organization.id, pending.id),
                  "Request withdrawn.",
                )}
              >
                Withdraw request
              </Button>
            )}
          </>
        )}

        {item.status === "approved" && (
          <>
            <Alert tone="success" title="Approved">
              Approved by {lastDecision?.decided_by_email ?? "a reviewer"}
              {lastDecision?.decided_at && ` on ${formatDateTime(lastDecision.decided_at)}`}.
            </Alert>
            {!isSocial(item.platform) ? (
              <p className="text-muted">
                {item.platform === "email" ? "Emails" : "Blog articles"} aren&apos;t sent from here:
                copy the approved text into your {item.platform === "email" ? "email" : "website"}{" "}
                tool. Plan the date in the calendar.
              </p>
            ) : can("publishing.publish") ? (
              <Button onClick={() => setPublishing(true)}>Publish or schedule</Button>
            ) : (
              <p className="text-muted">An owner or admin can publish this.</p>
            )}
          </>
        )}

        {latestJob &&
          (item.status === "scheduled" ||
            item.status === "published" ||
            latestJob.status === "failed") && (
            <div className="flex flex-col gap-2 rounded-md border border-border p-3">
              <p className="flex flex-wrap items-center gap-2">
                <Badge tone={JOB_STATUS[latestJob.status].tone}>
                  {JOB_STATUS[latestJob.status].label}
                </Badge>
                {latestJob.is_mock && <Badge tone="warning">Simulation</Badge>}
                <span className="text-xs text-muted">{latestJob.account_name}</span>
              </p>
              {latestJob.status === "scheduled" && latestJob.scheduled_for && (
                <p>Publishes {formatDateTime(latestJob.scheduled_for)}.</p>
              )}
              {latestJob.error_message && (
                <p className="text-xs text-muted">{latestJob.error_message}</p>
              )}
              <div className="flex flex-wrap items-center gap-2">
                {latestJob.permalink && (
                  <a
                    href={latestJob.permalink}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-primary hover:underline"
                  >
                    View post ↗
                  </a>
                )}
                {can("publishing.publish") &&
                  (latestJob.status === "scheduled" || latestJob.status === "queued") && (
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={run(
                        () => cancelJob(organization.id, latestJob.id),
                        "Publishing cancelled.",
                      )}
                    >
                      Cancel publishing
                    </Button>
                  )}
                <Link
                  href={`/o/${organization.id}/publishing`}
                  className="text-xs text-muted hover:text-foreground"
                >
                  Publishing history
                </Link>
              </div>
            </div>
          )}

        {item.status === "archived"
          ? can("content.edit") && (
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="secondary"
                  onClick={run(
                    () => unarchiveContent(organization.id, item.id),
                    "Restored to drafts.",
                  )}
                >
                  Restore to drafts
                </Button>
                <Button variant="danger" onClick={() => setConfirmDelete(true)}>
                  Delete permanently
                </Button>
              </div>
            )
          : can("content.edit") &&
            item.status !== "scheduled" && (
              <div className="flex flex-wrap gap-2 border-t border-border pt-3">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={run(() => archiveContent(organization.id, item.id), "Archived.")}
                >
                  Archive
                </Button>
                {item.status === "draft" && (
                  <Button variant="ghost" size="sm" onClick={() => setConfirmDelete(true)}>
                    Delete
                  </Button>
                )}
              </div>
            )}
      </div>
      {publishing && <PublishDialog item={item} onClose={() => setPublishing(false)} />}
      <ConfirmDialog
        open={confirmDelete}
        onCancel={() => setConfirmDelete(false)}
        onConfirm={() => remove.mutate()}
        pending={remove.isPending}
        title="Delete this content?"
        description="All versions and media are permanently deleted. This can't be undone."
        confirmLabel="Delete"
      />
    </Card>
  );
}
