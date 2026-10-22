"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { MockAIBadge } from "@/components/features/ai-badges";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input, Select, Textarea } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { useToast } from "@/components/ui/toast";
import { useOrg } from "@/hooks/use-org";
import { useWorkflowRun } from "@/hooks/use-workflow-run";
import {
  type ContentItem,
  listCampaigns,
  regenerateContent,
  restoreVersion,
  updateContentMeta,
} from "@/lib/api/content";
import { errorMessage } from "@/lib/api/errors";
import { formatDateTime } from "@/lib/format";

import { useRefreshItem, useVersions } from "./queries";

const SOURCE_LABEL = { manual: "Manual", ai: "AI", ai_edited: "AI, edited" } as const;
const EDITABLE = new Set(["draft", "in_review", "changes_requested", "approved"]);

/** datetime-local needs "YYYY-MM-DDTHH:mm" in local time. */
function toLocalInput(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function ChecksPanel({ item }: { item: ContentItem }) {
  const checks = item.current_version?.checks ?? [];
  return (
    <Card>
      <CardHeader title="Checks" description="Platform rules and your brand restrictions." />
      {checks.length === 0 ? (
        <p className="text-sm text-success">✓ No issues found.</p>
      ) : (
        <ul className="flex flex-col gap-2 text-sm">
          {checks.map((c, i) => (
            <li key={i} className="flex items-start gap-2">
              <Badge tone={c.severity === "error" ? "danger" : "warning"}>
                {c.severity === "error" ? "Fix" : "Check"}
              </Badge>
              <span>{c.message}</span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

export function DetailsPanel({ item }: { item: ContentItem }) {
  const { organization, can } = useOrg();
  const toast = useToast();
  const refresh = useRefreshItem();
  const campaigns = useQuery({
    queryKey: ["orgs", organization.id, "campaigns"],
    queryFn: () => listCampaigns(organization.id),
  });
  const [title, setTitle] = useState(item.title);
  const [campaign, setCampaign] = useState(item.campaign ?? "");
  const [planned, setPlanned] = useState(toLocalInput(item.planned_for));
  const [saving, setSaving] = useState(false);
  const editable =
    can("content.edit") && item.status !== "published" && item.status !== "scheduled";

  const dirty =
    title !== item.title ||
    campaign !== (item.campaign ?? "") ||
    planned !== toLocalInput(item.planned_for);

  const save = async () => {
    setSaving(true);
    try {
      await updateContentMeta(organization.id, item.id, {
        title: title.trim() || item.title,
        campaign: campaign || null,
        planned_for: planned ? new Date(planned).toISOString() : null,
      });
      await refresh();
      toast("Details saved.");
    } catch (e) {
      toast(errorMessage(e), "danger");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card>
      <CardHeader title="Details" />
      <fieldset disabled={!editable} className="flex flex-col gap-3">
        <Field label="Working title">
          {(p) => <Input value={title} onChange={(e) => setTitle(e.target.value)} {...p} />}
        </Field>
        <Field label="Campaign" optional>
          {(p) => (
            <Select value={campaign} onChange={(e) => setCampaign(e.target.value)} {...p}>
              <option value="">No campaign</option>
              {campaigns.data?.results.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </Select>
          )}
        </Field>
        <Field
          label="Planned for"
          optional
          hint="Places it on the calendar. Publishing is scheduled separately."
        >
          {(p) => (
            <Input
              type="datetime-local"
              value={planned}
              onChange={(e) => setPlanned(e.target.value)}
              {...p}
            />
          )}
        </Field>
        {editable && (
          <div>
            <Button size="sm" variant="secondary" onClick={save} disabled={!dirty || saving}>
              Save details
            </Button>
          </div>
        )}
      </fieldset>
    </Card>
  );
}

export function HistoryPanel({ item }: { item: ContentItem }) {
  const { organization, can } = useOrg();
  const toast = useToast();
  const refresh = useRefreshItem();
  const versions = useVersions(item.id);
  const editable = can("content.edit") && EDITABLE.has(item.status);

  const restore = async (n: number) => {
    try {
      const v = await restoreVersion(organization.id, item.id, n);
      await refresh();
      toast(`Version ${n} restored as version ${v.number}.`);
    } catch (e) {
      toast(errorMessage(e), "danger");
    }
  };

  return (
    <Card>
      <CardHeader title="Version history" description="Every save is kept." />
      {versions.isPending && <Spinner />}
      <ul className="flex flex-col divide-y divide-border">
        {versions.data?.map((v) => (
          <li key={v.id} className="py-2">
            <details>
              <summary className="flex cursor-pointer flex-wrap items-center gap-2 text-sm">
                <span className="font-medium">v{v.number}</span>
                <Badge>{SOURCE_LABEL[v.source]}</Badge>
                {v.is_mock && <MockAIBadge isMock />}
                {v.id === item.current_version?.id && <Badge tone="info">Current</Badge>}
                <span className="text-xs text-muted">
                  {v.created_by_email ?? "AI"} · {formatDateTime(v.created_at)}
                </span>
              </summary>
              <div className="mt-2 flex flex-col gap-2 pl-2">
                {v.note && <p className="text-xs text-muted">{v.note}</p>}
                <p className="text-sm whitespace-pre-line">{v.caption || "—"}</p>
                {editable && v.id !== item.current_version?.id && (
                  <div>
                    <Button size="sm" variant="secondary" onClick={() => restore(v.number)}>
                      Restore this version
                    </Button>
                  </div>
                )}
              </div>
            </details>
          </li>
        ))}
      </ul>
    </Card>
  );
}

export function RegenerateDialog({ item, onClose }: { item: ContentItem; onClose: () => void }) {
  const { organization } = useOrg();
  const queryClient = useQueryClient();
  const toast = useToast();
  const [instructions, setInstructions] = useState("");
  const [runId, setRunId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const run = useWorkflowRun(organization.id, runId);

  useEffect(() => {
    if (run.data?.status === "succeeded") {
      void queryClient.invalidateQueries({ queryKey: ["orgs", organization.id, "content"] });
      toast("New AI version added.");
      onClose();
    }
  }, [run.data, organization.id, queryClient, toast, onClose]);

  const start = async () => {
    setError(null);
    try {
      setRunId((await regenerateContent(organization.id, item.id, instructions)).id);
    } catch (e) {
      setError(errorMessage(e));
    }
  };
  const working = runId !== null && run.data?.status !== "failed";

  return (
    <Dialog
      open
      onClose={() => !working && onClose()}
      title="Regenerate with AI"
      description="Creates a new version. The current text stays in the history."
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={working}>
            Cancel
          </Button>
          <Button onClick={start} disabled={working}>
            {working ? "Working…" : "Regenerate"}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <Field
          label="What should change?"
          optional
          hint="e.g. 'Shorter and more playful' or 'Mention free parking'."
        >
          {(p) => (
            <Textarea
              rows={3}
              value={instructions}
              onChange={(e) => setInstructions(e.target.value)}
              disabled={working}
              {...p}
            />
          )}
        </Field>
        {working && (
          <p className="flex items-center gap-2 text-sm text-muted">
            <Spinner /> Writing…
          </p>
        )}
        {error && <Alert tone="danger">{error}</Alert>}
        {run.data?.status === "failed" && <Alert tone="danger">{run.data.error_message}</Alert>}
      </div>
    </Dialog>
  );
}
