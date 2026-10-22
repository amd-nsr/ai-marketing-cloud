"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { MockAIBadge } from "@/components/features/ai-badges";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Textarea } from "@/components/ui/input";
import { PageHeader } from "@/components/ui/page-header";
import { PageLoading } from "@/components/ui/spinner";
import { Tabs } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/toast";
import { useOrg } from "@/hooks/use-org";
import { type Approval, approveContent, listApprovals, rejectContent } from "@/lib/api/content";
import { errorMessage } from "@/lib/api/errors";
import { formatDateTime } from "@/lib/format";
import { PlatformBadge } from "@/features/content/labels";

type Tab = "pending" | "approved" | "rejected";

function ApprovalCard({ approval }: { approval: Approval }) {
  const { organization, can } = useOrg();
  const queryClient = useQueryClient();
  const toast = useToast();
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const v = approval.version;

  const decide = async (approve: boolean) => {
    setBusy(true);
    try {
      if (approve) await approveContent(organization.id, approval.id, comment);
      else await rejectContent(organization.id, approval.id, comment);
      toast(approve ? "Approved." : "Changes requested.");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["orgs", organization.id, "approvals"] }),
        queryClient.invalidateQueries({ queryKey: ["orgs", organization.id, "content"] }),
      ]);
    } catch (e) {
      toast(errorMessage(e), "danger");
    } finally {
      setBusy(false);
    }
  };

  const errors = v.checks.filter((c) => c.severity === "error");

  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <Link
            href={`/o/${organization.id}/content/${approval.item}`}
            className="font-medium hover:underline"
          >
            {approval.item_title}
          </Link>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted">
            <PlatformBadge platform={approval.item_platform} format={approval.item_format} />
            <span>Version {v.number}</span>
            <MockAIBadge isMock={v.is_mock} />
            <span>
              by {approval.requested_by_email ?? "a teammate"} ·{" "}
              {formatDateTime(approval.created_at)}
            </span>
          </div>
        </div>
        {approval.status !== "pending" && (
          <Badge tone={approval.status === "approved" ? "success" : "warning"}>
            {approval.status === "approved" ? "Approved" : "Changes requested"}
          </Badge>
        )}
      </div>
      {approval.request_note && (
        <p className="mt-3 rounded bg-neutral-soft p-2 text-sm">“{approval.request_note}”</p>
      )}
      <div className="mt-3 rounded-md border border-border p-3 text-sm">
        {v.hook && <p className="font-medium">{v.hook}</p>}
        <p className="whitespace-pre-line">{v.caption}</p>
        {v.cta && <p className="mt-1 font-medium">{v.cta}</p>}
        {v.hashtags.length > 0 && <p className="mt-1 text-primary">{v.hashtags.join(" ")}</p>}
      </div>
      {v.checks.length > 0 && (
        <ul className="mt-3 flex flex-col gap-1 text-xs">
          {v.checks.map((c, i) => (
            <li key={i} className={c.severity === "error" ? "text-danger" : "text-warning"}>
              {c.severity === "error" ? "✗" : "!"} {c.message}
            </li>
          ))}
        </ul>
      )}
      {approval.status === "pending" && can("content.approve") && (
        <div className="mt-4 flex flex-col gap-2">
          <Textarea
            aria-label={`Comment for ${approval.item_title}`}
            rows={2}
            placeholder="Comment (required to request changes)"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
          />
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => decide(true)} disabled={busy || errors.length > 0}>
              Approve
            </Button>
            <Button
              variant="secondary"
              onClick={() => decide(false)}
              disabled={busy || !comment.trim()}
            >
              Request changes
            </Button>
          </div>
        </div>
      )}
      {approval.status !== "pending" && approval.comment && (
        <p className="mt-3 text-sm text-muted">
          {approval.decided_by_email}: “{approval.comment}”
        </p>
      )}
    </Card>
  );
}

export function ApprovalsPage() {
  const { organization, can } = useOrg();
  const [tab, setTab] = useState<Tab>("pending");
  const approvals = useQuery({
    queryKey: ["orgs", organization.id, "approvals", tab],
    queryFn: () => listApprovals(organization.id, tab),
  });
  return (
    <>
      <PageHeader
        title="Approvals"
        description={
          can("content.approve")
            ? "Review exactly what will be published. Editing content after submission cancels its request."
            : "Content waiting for an owner or admin to review."
        }
      />
      <Tabs
        label="Approval status"
        value={tab}
        onChange={setTab}
        items={[
          {
            value: "pending",
            label: "Waiting",
            count: tab === "pending" ? approvals.data?.count : undefined,
          },
          { value: "approved", label: "Approved" },
          { value: "rejected", label: "Changes requested" },
        ]}
      />
      <div className="mt-4 flex flex-col gap-4">
        {approvals.isPending && <PageLoading />}
        {approvals.isError && <Alert tone="danger">{errorMessage(approvals.error)}</Alert>}
        {approvals.data?.count === 0 && (
          <EmptyState
            title={tab === "pending" ? "Nothing waiting for review" : "Nothing here yet"}
          />
        )}
        {approvals.data?.results.map((a) => (
          <ApprovalCard key={a.id} approval={a} />
        ))}
      </div>
    </>
  );
}
