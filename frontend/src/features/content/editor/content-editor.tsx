"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { AIGeneratedBadge } from "@/components/features/ai-badges";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input, Select } from "@/components/ui/input";
import { PageLoading } from "@/components/ui/spinner";
import { Tabs } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/toast";
import { useOrg } from "@/hooks/use-org";
import {
  type ContentFormat,
  type ContentItem,
  type ContentPlatform,
  duplicateContent,
} from "@/lib/api/content";
import { errorMessage } from "@/lib/api/errors";

import { FORMAT_LABEL, PLATFORM_FORMATS, PLATFORM_LABEL, PlatformBadge } from "../labels";
import { DesignEditor } from "../studio/design-editor";
import { VideoEditor } from "../studio/video-editor";
import { MediaPanel } from "./media-panel";
import { useAssets, useContentItem } from "./queries";
import { ChecksPanel, DetailsPanel, HistoryPanel, RegenerateDialog } from "./side-panels";
import { VersionEditor } from "./version-editor";
import { WorkflowPanel } from "./workflow-panel";

const EDITABLE = new Set(["draft", "in_review", "changes_requested", "approved"]);
type StudioTab = "write" | "visual" | "preview";

function Preview({ item }: { item: ContentItem }) {
  const { organization } = useOrg();
  const toast = useToast();
  const assets = useAssets(item.id);
  const v = item.current_version;
  const [index, setIndex] = useState(0);
  const media = assets.data ?? [];
  const current = media[Math.min(index, Math.max(media.length - 1, 0))];

  if (item.platform === "blog" || item.platform === "email") {
    const text = [
      item.platform === "email" ? `Subject: ${v?.headline ?? ""}` : `# ${v?.headline ?? ""}`,
      v?.hook ?? "",
      v?.caption ?? "",
      v?.cta ?? "",
    ]
      .filter(Boolean)
      .join("\n\n");
    return (
      <Card>
        <CardHeader
          title="Preview"
          description={item.platform === "email" ? "Email as it will be sent." : "Article text."}
          actions={
            <Button
              size="sm"
              variant="secondary"
              onClick={() => {
                void navigator.clipboard.writeText(text).then(() => toast("Copied to clipboard."));
              }}
            >
              Copy text
            </Button>
          }
        />
        <article className="mx-auto max-w-2xl rounded-lg border border-border p-5 text-sm">
          {item.platform === "email" ? (
            <>
              <p className="text-xs text-muted">Subject</p>
              <p className="font-semibold">{v?.headline || "No subject yet"}</p>
              {v?.hook && <p className="text-xs text-muted">{v.hook}</p>}
              <hr className="my-3 border-border" />
            </>
          ) : (
            <h3 className="mb-2 text-xl font-semibold">{v?.headline || "Untitled article"}</h3>
          )}
          {item.platform === "blog" && v?.hook && <p className="mb-3 text-muted">{v.hook}</p>}
          <p className="whitespace-pre-line">{v?.caption}</p>
          {v?.cta && <p className="mt-3 font-medium">{v.cta}</p>}
        </article>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader
        title="Preview"
        description={`Approximate ${PLATFORM_LABEL[item.platform]} rendering with the media that will be published.`}
      />
      <div className="mx-auto max-w-sm overflow-hidden rounded-lg border border-border">
        <div className="flex items-center gap-2 p-3">
          <span
            aria-hidden
            className="flex size-8 items-center justify-center rounded-full bg-primary text-xs font-semibold text-primary-foreground"
          >
            {organization.name.slice(0, 1).toUpperCase()}
          </span>
          <span className="text-sm font-medium">{organization.name}</span>
        </div>
        <div className="relative">
          {current?.content_type.startsWith("video/") ? (
            <video src={current.file_url} controls playsInline className="w-full bg-black" />
          ) : current ? (
            // eslint-disable-next-line @next/next/no-img-element -- authenticated same-origin file
            <img
              src={current.file_url}
              alt={v?.alt_text || "Post image"}
              className="w-full bg-neutral-soft object-cover"
              style={{
                aspectRatio:
                  current.width && current.height
                    ? `${current.width} / ${current.height}`
                    : "1 / 1",
              }}
            />
          ) : (
            <div className="flex aspect-square items-center justify-center bg-neutral-soft p-6 text-center text-xs text-muted">
              {item.document_kind
                ? "Export the design (or render the video) to see it here."
                : v?.creative_brief
                  ? `Visual to create: ${v.creative_brief}`
                  : "No image yet"}
            </div>
          )}
          {media.length > 1 && (
            <>
              <button
                type="button"
                aria-label="Previous slide"
                disabled={index === 0}
                onClick={() => setIndex(index - 1)}
                className="absolute top-1/2 left-2 -translate-y-1/2 rounded-full bg-black/50 px-2 text-white disabled:opacity-30"
              >
                ‹
              </button>
              <button
                type="button"
                aria-label="Next slide"
                disabled={index >= media.length - 1}
                onClick={() => setIndex(index + 1)}
                className="absolute top-1/2 right-2 -translate-y-1/2 rounded-full bg-black/50 px-2 text-white disabled:opacity-30"
              >
                ›
              </button>
              <span className="absolute top-2 right-2 rounded-full bg-black/60 px-2 text-xs text-white">
                {index + 1}/{media.length}
              </span>
            </>
          )}
        </div>
        <div className="p-3 text-sm">
          {v?.hook && <p className="font-medium">{v.hook}</p>}
          <p className="whitespace-pre-line">{v?.caption}</p>
          {v?.cta && <p className="mt-1 font-medium">{v.cta}</p>}
          {v && v.hashtags.length > 0 && (
            <p className="mt-1 text-primary">{v.hashtags.join(" ")}</p>
          )}
        </div>
      </div>
    </Card>
  );
}

function DuplicateDialog({ item, onClose }: { item: ContentItem; onClose: () => void }) {
  const { organization } = useOrg();
  const router = useRouter();
  const [platform, setPlatform] = useState<ContentPlatform>(item.platform);
  const [format, setFormat] = useState<ContentFormat>(item.format);
  const [title, setTitle] = useState(`${item.title} (copy)`);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const adapting = platform !== item.platform || format !== item.format;

  const go = async () => {
    setPending(true);
    setError(null);
    try {
      const copy = await duplicateContent(organization.id, item.id, { title, platform, format });
      router.push(`/o/${organization.id}/content/${copy.id}`);
    } catch (e) {
      setError(errorMessage(e));
      setPending(false);
    }
  };

  return (
    <Dialog
      open
      onClose={onClose}
      title="Duplicate or adapt"
      description="Creates a new draft in the same campaign. Exports and approvals aren't copied."
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={go} disabled={pending}>
            {adapting ? "Create adaptation" : "Duplicate"}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        {error && <Alert tone="danger">{error}</Alert>}
        <Field label="Title">
          {(p) => <Input value={title} onChange={(e) => setTitle(e.target.value)} {...p} />}
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Channel">
            {(p) => (
              <Select
                value={platform}
                onChange={(e) => {
                  const next = e.target.value as ContentPlatform;
                  setPlatform(next);
                  if (!PLATFORM_FORMATS[next].includes(format))
                    setFormat(PLATFORM_FORMATS[next][0]);
                }}
                {...p}
              >
                {(Object.keys(PLATFORM_LABEL) as ContentPlatform[]).map((pl) => (
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
        {adapting && (
          <p className="text-xs text-muted">
            The text is copied; the design is kept when the new format uses the same kind of design.
            Use AI assist or Regenerate to tailor the copy for {PLATFORM_LABEL[platform]}.
          </p>
        )}
      </div>
    </Dialog>
  );
}

export function ContentEditor({ itemId }: { itemId: string }) {
  const { organization, can } = useOrg();
  const params = useSearchParams();
  const item = useContentItem(itemId);
  const [regenerating, setRegenerating] = useState(false);
  const [duplicating, setDuplicating] = useState(false);
  const initialTab = params.get("tab");
  const [tab, setTab] = useState<StudioTab>(
    initialTab === "visual" || initialTab === "preview" ? initialTab : "write",
  );

  if (item.isPending) return <PageLoading />;
  if (item.isError) return <Alert tone="danger">{errorMessage(item.error)}</Alert>;
  const data = item.data;
  const v = data.current_version;
  const kind = data.document_kind;
  const visualLabel = kind === "carousel" ? "Carousel" : kind === "video" ? "Video" : "Design";

  const tabs: { value: StudioTab; label: string }[] = [
    { value: "write", label: "Write" },
    ...(kind ? [{ value: "visual" as const, label: visualLabel }] : []),
    { value: "preview", label: "Preview" },
  ];

  return (
    <>
      <Link href={`/o/${organization.id}/content`} className="text-sm text-primary hover:underline">
        ← Content studio
      </Link>
      <header className="mt-3 mb-4 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold tracking-tight">{data.title}</h1>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted">
            <PlatformBadge platform={data.platform} format={data.format} />
            {v && v.source !== "manual" && (
              <AIGeneratedBadge model={v.ai_model} isMock={v.is_mock} />
            )}
            {v && <span>Version {v.number}</span>}
            {data.campaign_name && (
              <Link
                href={`/o/${organization.id}/content?view=campaigns&campaign=${data.campaign}`}
                className="text-primary hover:underline"
              >
                · {data.campaign_name}
              </Link>
            )}
          </div>
        </div>
        {can("content.edit") && (
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={() => setDuplicating(true)}>
              Duplicate / adapt
            </Button>
            {EDITABLE.has(data.status) && (
              <Button variant="secondary" onClick={() => setRegenerating(true)}>
                Regenerate with AI
              </Button>
            )}
          </div>
        )}
      </header>

      <div className="mb-4">
        <Tabs label="Studio" value={tab} onChange={setTab} items={tabs} />
      </div>

      {tab === "visual" && kind && (
        <div className="mb-6">
          {kind === "video" ? (
            <VideoEditor item={data} />
          ) : (
            <DesignEditor key={kind} item={data} kind={kind} />
          )}
        </div>
      )}
      {tab === "write" && (
        <Card className="mb-6">
          <VersionEditor item={data} />
        </Card>
      )}

      <div className="grid gap-6 xl:grid-cols-[1fr_22rem]">
        <div className="flex min-w-0 flex-col gap-6">
          <Preview item={data} />
        </div>
        <aside className="flex flex-col gap-6">
          <WorkflowPanel item={data} />
          <ChecksPanel item={data} />
          <MediaPanel item={data} />
          <DetailsPanel key={data.updated_at} item={data} />
          <HistoryPanel item={data} />
        </aside>
      </div>
      {regenerating && <RegenerateDialog item={data} onClose={() => setRegenerating(false)} />}
      {duplicating && <DuplicateDialog item={data} onClose={() => setDuplicating(false)} />}
    </>
  );
}
