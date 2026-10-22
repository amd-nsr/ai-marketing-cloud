"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useState } from "react";

import { MockAIBadge } from "@/components/features/ai-badges";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { Field } from "@/components/ui/field";
import { Input, Select } from "@/components/ui/input";
import { PageHeader } from "@/components/ui/page-header";
import { PageLoading } from "@/components/ui/spinner";
import { Tabs } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/toast";
import { useOrg } from "@/hooks/use-org";
import type { Platform } from "@/lib/api/brand";
import { type ContentFormat, createContent, listCampaigns, listContent } from "@/lib/api/content";
import { errorMessage } from "@/lib/api/errors";
import { formatDateTime } from "@/lib/format";

import { GenerateContentDialog } from "./generate-content-dialog";
import {
  FORMAT_LABEL,
  IssueSummary,
  PLATFORM_FORMATS,
  PLATFORM_LABEL,
  PlatformBadge,
  StatusBadge,
} from "./labels";

type Tab =
  | "all"
  | "draft"
  | "in_review"
  | "changes_requested"
  | "approved"
  | "scheduled"
  | "published"
  | "archived";
const TABS: { value: Tab; label: string }[] = [
  { value: "all", label: "All" },
  { value: "draft", label: "Drafts" },
  { value: "in_review", label: "Awaiting approval" },
  { value: "changes_requested", label: "Changes requested" },
  { value: "approved", label: "Approved" },
  { value: "scheduled", label: "Scheduled" },
  { value: "published", label: "Published" },
  { value: "archived", label: "Archived" },
];

function NewContentDialog({ onClose }: { onClose: () => void }) {
  const { organization } = useOrg();
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [platform, setPlatform] = useState<Platform>("instagram");
  const [format, setFormat] = useState<ContentFormat>("post");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const create = async () => {
    if (!title.trim()) return setError("Give it a working title.");
    setPending(true);
    try {
      const item = await createContent(organization.id, { title: title.trim(), platform, format });
      router.push(`/o/${organization.id}/content/${item.id}`);
    } catch (e) {
      setError(errorMessage(e));
      setPending(false);
    }
  };

  return (
    <Dialog
      open
      onClose={onClose}
      title="New content"
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={create} disabled={pending}>
            Create and edit
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        {error && <Alert tone="danger">{error}</Alert>}
        <Field label="Working title">
          {(p) => <Input value={title} onChange={(e) => setTitle(e.target.value)} {...p} />}
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Platform">
            {(p) => (
              <Select
                value={platform}
                onChange={(e) => {
                  const next = e.target.value as Platform;
                  setPlatform(next);
                  if (!PLATFORM_FORMATS[next].includes(format))
                    setFormat(PLATFORM_FORMATS[next][0]);
                }}
                {...p}
              >
                {(Object.keys(PLATFORM_LABEL) as Platform[]).map((pl) => (
                  <option key={pl} value={pl}>
                    {PLATFORM_LABEL[pl]}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Field label="Format">
            {(p) => (
              <Select
                value={format}
                onChange={(e) => setFormat(e.target.value as ContentFormat)}
                {...p}
              >
                {PLATFORM_FORMATS[platform].map((f) => (
                  <option key={f} value={f}>
                    {FORMAT_LABEL[f]}
                  </option>
                ))}
              </Select>
            )}
          </Field>
        </div>
      </div>
    </Dialog>
  );
}

export function ContentStudio() {
  const { organization, can } = useOrg();
  const toast = useToast();
  const [tab, setTab] = useState<Tab>("all");
  const [platform, setPlatform] = useState("");
  const params = useSearchParams();
  const [campaign, setCampaign] = useState(params.get("campaign") ?? "");
  const [q, setQ] = useState("");
  const [dialog, setDialog] = useState<"generate" | "new" | null>(null);

  const filters = { status: tab === "all" ? undefined : tab, platform, campaign, q: q.trim() };
  const content = useQuery({
    queryKey: ["orgs", organization.id, "content", filters],
    queryFn: () => listContent(organization.id, filters),
  });
  const campaigns = useQuery({
    queryKey: ["orgs", organization.id, "campaigns"],
    queryFn: () => listCampaigns(organization.id),
  });

  const onGenerated = useCallback(
    (ids: string[]) => {
      setDialog(null);
      setTab("draft");
      toast(`${ids.length} draft${ids.length === 1 ? "" : "s"} created.`);
    },
    [toast],
  );

  const canEdit = can("content.edit");

  return (
    <>
      <PageHeader
        title="Content studio"
        description="Write, generate, review, and organize posts for each platform."
        actions={
          canEdit && (
            <>
              <Button variant="secondary" onClick={() => setDialog("new")}>
                New content
              </Button>
              <Button onClick={() => setDialog("generate")}>Generate with AI</Button>
            </>
          )
        }
      />
      <Tabs label="Content status" value={tab} onChange={setTab} items={TABS} />
      <div className="mt-4 mb-4 flex flex-wrap gap-2">
        <Input
          aria-label="Search content"
          placeholder="Search titles and captions"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          className="w-full sm:w-64"
        />
        <Select
          aria-label="Platform"
          value={platform}
          onChange={(e) => setPlatform(e.target.value)}
          className="w-40"
        >
          <option value="">All platforms</option>
          {(Object.keys(PLATFORM_LABEL) as Platform[]).map((p) => (
            <option key={p} value={p}>
              {PLATFORM_LABEL[p]}
            </option>
          ))}
        </Select>
        {campaigns.data && campaigns.data.count > 0 && (
          <Select
            aria-label="Campaign"
            value={campaign}
            onChange={(e) => setCampaign(e.target.value)}
            className="w-48"
          >
            <option value="">All campaigns</option>
            {campaigns.data.results.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </Select>
        )}
      </div>

      {content.isPending && <PageLoading />}
      {content.isError && <Alert tone="danger">{errorMessage(content.error)}</Alert>}
      {content.data && content.data.count === 0 && (
        <EmptyState
          title={
            tab === "all" && !q && !platform && !campaign
              ? "No content yet"
              : "Nothing matches these filters"
          }
          description="Generate drafts from a short brief, or write one yourself."
          action={
            canEdit && <Button onClick={() => setDialog("generate")}>Generate with AI</Button>
          }
        />
      )}
      {content.data && content.data.count > 0 && (
        <ul className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {content.data.results.map((item) => (
            <li key={item.id}>
              <Link
                href={`/o/${organization.id}/content/${item.id}`}
                className="flex h-full flex-col gap-2 rounded-lg border border-border bg-surface p-4 transition hover:border-primary"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <StatusBadge status={item.status} />
                  <PlatformBadge platform={item.platform} format={item.format} />
                  {item.current_version && <MockAIBadge isMock={item.current_version.is_mock} />}
                </div>
                <p className="font-medium">{item.title}</p>
                <p className="line-clamp-3 text-sm text-muted">
                  {item.current_version?.caption || "No caption yet."}
                </p>
                <div className="mt-auto flex flex-wrap items-center justify-between gap-2 pt-2 text-xs text-muted">
                  <span>{item.campaign_name ?? "No campaign"}</span>
                  {item.current_version && <IssueSummary checks={item.current_version.checks} />}
                </div>
                <p className="text-xs text-muted">
                  {item.planned_for
                    ? `Planned ${formatDateTime(item.planned_for)}`
                    : `Updated ${formatDateTime(item.updated_at)}`}
                </p>
              </Link>
            </li>
          ))}
        </ul>
      )}

      {dialog === "generate" && (
        <GenerateContentDialog onClose={() => setDialog(null)} onGenerated={onGenerated} />
      )}
      {dialog === "new" && <NewContentDialog onClose={() => setDialog(null)} />}
    </>
  );
}
