"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useState } from "react";

import { MockAIBadge } from "@/components/features/ai-badges";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { Field } from "@/components/ui/field";
import { Input, Select } from "@/components/ui/input";
import { PageHeader } from "@/components/ui/page-header";
import { PageLoading } from "@/components/ui/spinner";
import { Tabs } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/toast";
import { useOrg } from "@/hooks/use-org";
import {
  type ContentFormat,
  type ContentItem,
  type ContentPlatform,
  createContent,
  duplicateContent,
  listCampaigns,
  listContent,
} from "@/lib/api/content";
import { errorMessage } from "@/lib/api/errors";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

import { GenerateContentDialog } from "./generate-content-dialog";
import {
  DOCUMENT_KIND,
  FORMAT_LABEL,
  IssueSummary,
  PLATFORM_FORMATS,
  PLATFORM_LABEL,
  PlatformBadge,
  StatusBadge,
} from "./labels";
import { PhoneFrame } from "./studio/design-panels";
import { LibraryBrowser } from "./studio/library-browser";

type StatusTab =
  | "all"
  | "draft"
  | "in_review"
  | "changes_requested"
  | "approved"
  | "scheduled"
  | "published"
  | "archived";
const STATUS_TABS: { value: StatusTab; label: string }[] = [
  { value: "all", label: "All" },
  { value: "draft", label: "Drafts" },
  { value: "in_review", label: "Awaiting approval" },
  { value: "changes_requested", label: "Changes requested" },
  { value: "approved", label: "Approved" },
  { value: "scheduled", label: "Scheduled" },
  { value: "published", label: "Published" },
  { value: "archived", label: "Archived" },
];

type View = "content" | "campaigns" | "library";
type Mode = "write" | "design" | "carousel" | "video";

/** What each studio entry point creates: allowed channels and formats. */
const MODES: Record<
  Mode,
  { title: string; description: string; formats: Partial<Record<ContentPlatform, ContentFormat[]>> }
> = {
  write: {
    title: "Write",
    description: "Captions, posts, articles, and emails",
    formats: {
      instagram: ["post", "story"],
      facebook: ["post", "story"],
      tiktok: ["short_video"],
      blog: ["article"],
      email: ["newsletter"],
    },
  },
  design: {
    title: "Design",
    description: "Graphics from templates, uploads, and your brand",
    formats: { instagram: ["post", "story"], facebook: ["post", "story"] },
  },
  carousel: {
    title: "Carousel",
    description: "Multi-slide posts, each slide editable",
    formats: { instagram: ["carousel"], facebook: ["carousel"], tiktok: ["carousel"] },
  },
  video: {
    title: "Video",
    description: "Short videos from your photos and clips",
    formats: { instagram: ["reel"], facebook: ["reel"], tiktok: ["short_video"] },
  },
};

const FORMAT_FILTERS: { value: string; label: string }[] = [
  { value: "", label: "All types" },
  { value: "post,story", label: "Posts and stories" },
  { value: "carousel", label: "Carousels" },
  { value: "reel,short_video", label: "Videos" },
  { value: "article,newsletter", label: "Articles and emails" },
];

function NewContentDialog({
  mode,
  defaultCampaign,
  onClose,
}: {
  mode: Mode;
  defaultCampaign?: string;
  onClose: () => void;
}) {
  const { organization } = useOrg();
  const router = useRouter();
  const spec = MODES[mode];
  const platforms = Object.keys(spec.formats) as ContentPlatform[];
  const [title, setTitle] = useState("");
  const [platform, setPlatform] = useState<ContentPlatform>(platforms[0]);
  const [format, setFormat] = useState<ContentFormat>(spec.formats[platforms[0]]![0]);
  const [campaign, setCampaign] = useState(defaultCampaign ?? "");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const campaigns = useQuery({
    queryKey: ["orgs", organization.id, "campaigns"],
    queryFn: () => listCampaigns(organization.id),
  });
  const formats = spec.formats[platform] ?? PLATFORM_FORMATS[platform];

  const create = async () => {
    if (!title.trim()) return setError("Give it a working title.");
    setPending(true);
    try {
      const item = await createContent(organization.id, {
        title: title.trim(),
        platform,
        format,
        campaign: campaign || null,
      });
      const tab = mode === "write" ? "write" : "visual";
      router.push(`/o/${organization.id}/content/${item.id}?tab=${tab}`);
    } catch (e) {
      setError(errorMessage(e));
      setPending(false);
    }
  };

  return (
    <Dialog
      open
      onClose={onClose}
      title={`New ${spec.title.toLowerCase() === "write" ? "copy" : spec.title.toLowerCase()}`}
      description={spec.description}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={create} disabled={pending}>
            Create and open
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        {error && <Alert tone="danger">{error}</Alert>}
        <Field label="Working title">
          {(p) => (
            <Input value={title} onChange={(e) => setTitle(e.target.value)} autoFocus {...p} />
          )}
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Channel">
            {(p) => (
              <Select
                value={platform}
                onChange={(e) => {
                  const next = e.target.value as ContentPlatform;
                  setPlatform(next);
                  const allowed = spec.formats[next] ?? [];
                  if (!allowed.includes(format)) setFormat(allowed[0]);
                }}
                {...p}
              >
                {platforms.map((pl) => (
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
                {formats.map((f) => (
                  <option key={f} value={f}>
                    {FORMAT_LABEL[f]}
                  </option>
                ))}
              </Select>
            )}
          </Field>
        </div>
        {campaigns.data && campaigns.data.count > 0 && (
          <Field label="Campaign" optional>
            {(p) => (
              <Select value={campaign} onChange={(e) => setCampaign(e.target.value)} {...p}>
                <option value="">No campaign</option>
                {campaigns.data.results.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </Select>
            )}
          </Field>
        )}
      </div>
    </Dialog>
  );
}

function ItemCard({ item, actions }: { item: ContentItem; actions?: React.ReactNode }) {
  const { organization } = useOrg();
  return (
    <div className="flex h-full flex-col overflow-hidden rounded-lg border border-border bg-surface transition hover:border-primary">
      <Link href={`/o/${organization.id}/content/${item.id}`} className="flex flex-1 flex-col">
        {(item.thumbnail_url ||
          (item.current_version && "kind" in item.current_version.document)) && (
          <Thumbnail item={item} className="aspect-[16/9] w-full bg-neutral-soft object-cover" />
        )}
        <div className="flex flex-1 flex-col gap-2 p-4">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge status={item.status} />
            <PlatformBadge platform={item.platform} format={item.format} />
            {item.current_version && <MockAIBadge isMock={item.current_version.is_mock} />}
          </div>
          <p className="font-medium">{item.title}</p>
          <p className="line-clamp-3 text-sm text-muted">
            {item.current_version?.caption || "No text yet."}
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
        </div>
      </Link>
      {actions && <div className="flex flex-wrap gap-2 border-t border-border p-2">{actions}</div>}
    </div>
  );
}

function ContentList({ onNew }: { onNew: () => void }) {
  const { organization, can } = useOrg();
  const params = useSearchParams();
  const [tab, setTab] = useState<StatusTab>("all");
  const [platform, setPlatform] = useState("");
  const [format, setFormat] = useState("");
  const [campaign, setCampaign] = useState(params.get("campaign") ?? "");
  const [q, setQ] = useState("");
  const filters = {
    status: tab === "all" ? undefined : tab,
    platform,
    format,
    campaign,
    q: q.trim(),
  };
  const content = useQuery({
    queryKey: ["orgs", organization.id, "content", filters],
    queryFn: () => listContent(organization.id, filters),
  });
  const campaigns = useQuery({
    queryKey: ["orgs", organization.id, "campaigns"],
    queryFn: () => listCampaigns(organization.id),
  });

  return (
    <>
      <Tabs label="Content status" value={tab} onChange={setTab} items={STATUS_TABS} />
      <div className="mt-4 mb-4 flex flex-wrap gap-2">
        <Input
          aria-label="Search content"
          placeholder="Search titles and captions"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          className="w-full sm:w-64"
        />
        <Select
          aria-label="Content type"
          value={format}
          onChange={(e) => setFormat(e.target.value)}
          className="w-full sm:w-48"
        >
          {FORMAT_FILTERS.map((f) => (
            <option key={f.value} value={f.value}>
              {f.label}
            </option>
          ))}
        </Select>
        <Select
          aria-label="Channel"
          value={platform}
          onChange={(e) => setPlatform(e.target.value)}
          className="w-full sm:w-40"
        >
          <option value="">All channels</option>
          {(Object.keys(PLATFORM_LABEL) as ContentPlatform[]).map((p) => (
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
            className="w-full sm:w-48"
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
            tab === "all" && !q && !platform && !campaign && !format
              ? "No content yet"
              : "Nothing matches these filters"
          }
          description="Pick a studio above, or generate drafts from a short brief."
          action={can("content.edit") && <Button onClick={onNew}>Generate with AI</Button>}
        />
      )}
      {content.data && content.data.count > 0 && (
        <ul className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {content.data.results.map((item) => (
            <li key={item.id}>
              <ItemCard item={item} />
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

/** The item's first publishable media (image or rendered video), or a placeholder. */
function Thumbnail({ item, className }: { item: ContentItem; className: string }) {
  const v = item.current_version;
  if (item.thumbnail_url && item.thumbnail_type === "video")
    return (
      <video src={item.thumbnail_url} muted playsInline preload="metadata" className={className} />
    );
  if (item.thumbnail_url)
    // eslint-disable-next-line @next/next/no-img-element -- authenticated same-origin file
    return <img src={item.thumbnail_url} alt="" loading="lazy" className={className} />;
  const hasDocument = Boolean(v && "kind" in v.document);
  return (
    <div
      className={cn(
        className,
        "flex items-center justify-center bg-neutral-soft p-4 text-center text-xs text-muted",
      )}
    >
      {hasDocument
        ? `${DOCUMENT_KIND[item.format] === "video" ? "Video" : "Design"} not exported yet`
        : v?.creative_brief
          ? `Visual to create: ${v.creative_brief.slice(0, 120)}`
          : "No visual yet"}
    </div>
  );
}

/** One campaign asset as it would appear on its channel. */
function CreativePreview({
  item,
  onVariation,
  busy,
}: {
  item: ContentItem;
  onVariation?: () => void;
  busy: boolean;
}) {
  const { organization } = useOrg();
  const v = item.current_version;
  const href = `/o/${organization.id}/content/${item.id}`;
  const longForm = item.platform === "blog" || item.platform === "email";
  return (
    <div className="flex flex-col gap-2">
      <Link href={href} className="block rounded-[2rem] transition hover:opacity-90">
        {longForm ? (
          <div className="rounded-lg border border-border bg-surface p-3 text-xs">
            <p className="text-muted">{item.platform === "email" ? "Subject" : "Article"}</p>
            <p className="font-semibold">{v?.headline || item.title}</p>
            <p className="mt-2 line-clamp-6 whitespace-pre-line text-muted">
              {v?.caption || "No text yet."}
            </p>
          </div>
        ) : (
          <PhoneFrame
            name={organization.name}
            platform={`${PLATFORM_LABEL[item.platform]} · ${FORMAT_LABEL[item.format]}`}
            footer={<p className="line-clamp-2">{v?.caption || "No caption yet."}</p>}
          >
            <Thumbnail item={item} className="aspect-square w-full object-cover" />
          </PhoneFrame>
        )}
      </Link>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex min-w-0 flex-wrap items-center gap-1.5">
          <StatusBadge status={item.status} />
          {v && <IssueSummary checks={v.checks} />}
        </div>
        {onVariation && (
          <Button size="sm" variant="ghost" disabled={busy} onClick={onVariation}>
            + Variation
          </Button>
        )}
      </div>
      <Link href={href} className="truncate text-xs font-medium hover:underline">
        {item.title}
      </Link>
    </div>
  );
}

function CampaignCreatives({
  campaignId,
  setCampaignId,
  onNew,
}: {
  campaignId: string;
  setCampaignId: (id: string) => void;
  onNew: (mode: Mode) => void;
}) {
  const { organization, can } = useOrg();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [generating, setGenerating] = useState(false);
  const campaigns = useQuery({
    queryKey: ["orgs", organization.id, "campaigns"],
    queryFn: () => listCampaigns(organization.id),
  });
  const campaign = campaigns.data?.results.find((c) => c.id === campaignId);
  const items = useQuery({
    queryKey: ["orgs", organization.id, "content", { campaign: campaignId, view: "creatives" }],
    queryFn: () => listContent(organization.id, { campaign: campaignId }),
    enabled: Boolean(campaignId),
  });
  const variation = useMutation({
    mutationFn: (item: ContentItem) =>
      duplicateContent(organization.id, item.id, { title: `${item.title} (variation)` }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["orgs", organization.id, "content"] });
      toast("Variation created as a new draft. Edit it to try a different angle.");
    },
    onError: (e) => toast(errorMessage(e), "danger"),
  });
  const onGenerated = useCallback(
    (ids: string[]) => {
      setGenerating(false);
      void queryClient.invalidateQueries({ queryKey: ["orgs", organization.id, "content"] });
      toast(`${ids.length} creative${ids.length === 1 ? "" : "s"} added to the campaign.`);
    },
    [queryClient, organization.id, toast],
  );

  if (campaigns.isPending) return <PageLoading />;
  if (!campaigns.data?.count)
    return (
      <EmptyState
        title="No campaigns yet"
        description="Create a campaign to plan a coordinated set of posts, carousels, and videos around one objective."
        action={
          <Link
            href={`/o/${organization.id}/campaigns`}
            className="text-sm text-primary hover:underline"
          >
            Go to campaigns →
          </Link>
        }
      />
    );

  const byPlatform = new Map<ContentPlatform, ContentItem[]>();
  for (const it of items.data?.results ?? []) {
    byPlatform.set(it.platform, [...(byPlatform.get(it.platform) ?? []), it]);
  }
  const counts = { design: 0, carousel: 0, video: 0, text: 0 };
  for (const it of items.data?.results ?? []) {
    const k = DOCUMENT_KIND[it.format];
    counts[k ?? "text"] += 1;
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-3">
        <Field label="Campaign" className="w-full sm:w-72">
          {(p) => (
            <Select value={campaignId} onChange={(e) => setCampaignId(e.target.value)} {...p}>
              <option value="">Choose a campaign</option>
              {campaigns.data.results.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </Select>
          )}
        </Field>
        {campaign && can("content.edit") && (
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => setGenerating(true)}>Generate creative set</Button>
            {(["design", "carousel", "video", "write"] as Mode[]).map((m) => (
              <Button key={m} variant="secondary" onClick={() => onNew(m)}>
                + {MODES[m].title}
              </Button>
            ))}
          </div>
        )}
      </div>

      {campaign && (
        <Card>
          <CardHeader
            title={campaign.name}
            description={campaign.objective || campaign.description || "No objective set."}
          />
          <div className="flex flex-wrap gap-2 text-xs">
            {campaign.platforms.map((p) => (
              <Badge key={p} tone={byPlatform.has(p) ? "success" : "warning"}>
                {PLATFORM_LABEL[p]}: {byPlatform.get(p)?.length ?? 0}
              </Badge>
            ))}
            <Badge>{counts.design} designs</Badge>
            <Badge>{counts.carousel} carousels</Badge>
            <Badge>{counts.video} videos</Badge>
            <Badge>{counts.text} text-only</Badge>
          </div>
          {campaign.key_messages.length > 0 && (
            <ul className="mt-3 list-disc pl-5 text-sm text-muted">
              {campaign.key_messages.map((m) => (
                <li key={m}>{m}</li>
              ))}
            </ul>
          )}
          <p className="mt-3 text-xs text-muted">
            Generated creatives share this campaign&apos;s objective and key messages plus your
            brand voice. Budgets, targeting, and ads stay in the ads module.
          </p>
        </Card>
      )}

      {items.data && items.data.count === 0 && (
        <EmptyState
          title="No creatives in this campaign yet"
          description="Generate a coordinated set (posts, carousels, video scripts) or create one asset at a time."
        />
      )}
      {byPlatform.size > 0 && (
        <div className="-mx-1 overflow-x-auto pb-2">
          <ol className="flex min-w-full gap-4 px-1" aria-label="Creatives by channel">
            {[...byPlatform.entries()].map(([platform, list]) => (
              <li
                key={platform}
                className="flex w-[19rem] shrink-0 flex-col gap-3 rounded-xl border border-border bg-neutral-soft/60 p-3"
              >
                <div className="flex items-center justify-between gap-2">
                  <h2 className="text-sm font-semibold">{PLATFORM_LABEL[platform]}</h2>
                  <Badge>
                    {list.length} creative{list.length === 1 ? "" : "s"}
                  </Badge>
                </div>
                {list.map((item) => (
                  <CreativePreview
                    key={item.id}
                    item={item}
                    onVariation={can("content.edit") ? () => variation.mutate(item) : undefined}
                    busy={variation.isPending}
                  />
                ))}
              </li>
            ))}
          </ol>
        </div>
      )}

      {generating && campaign && (
        <GenerateContentDialog
          onClose={() => setGenerating(false)}
          onGenerated={onGenerated}
          defaultCampaign={campaign.id}
          defaultTargets={campaign.platforms.flatMap((p) =>
            p === "tiktok"
              ? [`${p}:short_video` as const]
              : [`${p}:post` as const, `${p}:carousel` as const],
          )}
        />
      )}
    </div>
  );
}

export function ContentStudio() {
  const { can } = useOrg();
  const toast = useToast();
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const view = (params.get("view") as View | null) ?? "content";
  const [campaignId, setCampaignId] = useState(params.get("campaign") ?? "");
  const [dialog, setDialog] = useState<{ type: "generate" } | { type: "new"; mode: Mode } | null>(
    null,
  );

  const setView = (next: View) => {
    const sp = new URLSearchParams(params.toString());
    sp.set("view", next);
    router.replace(`${pathname}?${sp.toString()}`);
  };

  const onGenerated = useCallback(
    (ids: string[]) => {
      setDialog(null);
      toast(`${ids.length} draft${ids.length === 1 ? "" : "s"} created.`);
    },
    [toast],
  );

  const canEdit = can("content.edit");
  const entries: { mode: Mode | "campaign"; title: string; description: string }[] = [
    { mode: "write", title: MODES.write.title, description: MODES.write.description },
    { mode: "design", title: MODES.design.title, description: MODES.design.description },
    { mode: "carousel", title: MODES.carousel.title, description: MODES.carousel.description },
    { mode: "video", title: MODES.video.title, description: MODES.video.description },
    {
      mode: "campaign",

      title: "Campaign creatives",
      description: "A coordinated set of assets for one campaign",
    },
  ];

  return (
    <>
      <PageHeader
        title="Content studio"
        description="Write, design, and produce posts, carousels, videos, articles, and emails, then send them for approval and publishing."
        actions={
          canEdit && (
            <Button onClick={() => setDialog({ type: "generate" })}>Generate with AI</Button>
          )
        }
      />
      {canEdit && (
        <ul className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
          {entries.map((e) => (
            <li key={e.mode}>
              <button
                type="button"
                onClick={() =>
                  e.mode === "campaign"
                    ? setView("campaigns")
                    : setDialog({ type: "new", mode: e.mode })
                }
                className={cn(
                  "flex h-full w-full flex-col gap-1 rounded-lg border border-border bg-surface p-4 text-left transition hover:border-primary",
                  e.mode === "campaign" && view === "campaigns" && "border-primary",
                )}
              >
                <span className="font-medium">{e.title}</span>
                <span className="text-xs text-muted">{e.description}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="mb-4">
        <Tabs
          label="Studio sections"
          value={view}
          onChange={setView}
          items={[
            { value: "content", label: "All content" },
            { value: "campaigns", label: "Campaign creatives" },
            { value: "library", label: "Media library" },
          ]}
        />
      </div>

      {view === "content" && <ContentList onNew={() => setDialog({ type: "generate" })} />}
      {view === "campaigns" && (
        <CampaignCreatives
          campaignId={campaignId}
          setCampaignId={setCampaignId}
          onNew={(mode) => setDialog({ type: "new", mode })}
        />
      )}
      {view === "library" && (
        <Card>
          <CardHeader
            title="Media library"
            description="Photos, logos, clips, music, and AI images to reuse across designs, carousels, and videos. Brand kit assets are managed under Brand."
          />
          <LibraryBrowser />
        </Card>
      )}

      {dialog?.type === "generate" && (
        <GenerateContentDialog
          onClose={() => setDialog(null)}
          onGenerated={onGenerated}
          defaultCampaign={view === "campaigns" ? campaignId : undefined}
        />
      )}
      {dialog?.type === "new" && (
        <NewContentDialog
          mode={dialog.mode}
          defaultCampaign={view === "campaigns" ? campaignId : undefined}
          onClose={() => setDialog(null)}
        />
      )}
    </>
  );
}
