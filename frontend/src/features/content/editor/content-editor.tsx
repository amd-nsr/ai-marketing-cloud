"use client";

import Link from "next/link";
import { useState } from "react";

import { AIGeneratedBadge } from "@/components/features/ai-badges";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { PageLoading } from "@/components/ui/spinner";
import { useOrg } from "@/hooks/use-org";
import type { ContentItem } from "@/lib/api/content";
import { errorMessage } from "@/lib/api/errors";

import { PLATFORM_LABEL, PlatformBadge } from "../labels";
import { MediaPanel } from "./media-panel";
import { useAssets, useContentItem } from "./queries";
import { ChecksPanel, DetailsPanel, HistoryPanel, RegenerateDialog } from "./side-panels";
import { VersionEditor } from "./version-editor";
import { WorkflowPanel } from "./workflow-panel";

const EDITABLE = new Set(["draft", "in_review", "changes_requested", "approved"]);

function Preview({ item }: { item: ContentItem }) {
  const { organization } = useOrg();
  const assets = useAssets(item.id);
  const v = item.current_version;
  const image = assets.data?.[0];
  return (
    <Card>
      <CardHeader
        title="Preview"
        description={`Approximate ${PLATFORM_LABEL[item.platform]} rendering.`}
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
        {image ? (
          // eslint-disable-next-line @next/next/no-img-element -- authenticated same-origin file
          <img
            src={image.file_url}
            alt={v?.alt_text || "Post image"}
            className="aspect-square w-full object-cover"
          />
        ) : (
          <div className="flex aspect-square items-center justify-center bg-neutral-soft p-6 text-center text-xs text-muted">
            {v?.creative_brief ? `Visual to create: ${v.creative_brief}` : "No image yet"}
          </div>
        )}
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

export function ContentEditor({ itemId }: { itemId: string }) {
  const { organization, can } = useOrg();
  const item = useContentItem(itemId);
  const [regenerating, setRegenerating] = useState(false);

  if (item.isPending) return <PageLoading />;
  if (item.isError) return <Alert tone="danger">{errorMessage(item.error)}</Alert>;
  const data = item.data;
  const v = data.current_version;

  return (
    <>
      <Link href={`/o/${organization.id}/content`} className="text-sm text-primary hover:underline">
        ← Content studio
      </Link>
      <header className="mt-3 mb-6 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold tracking-tight">{data.title}</h1>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted">
            <PlatformBadge platform={data.platform} format={data.format} />
            {v && v.source !== "manual" && (
              <AIGeneratedBadge model={v.ai_model} isMock={v.is_mock} />
            )}
            {v && <span>Version {v.number}</span>}
            {data.campaign_name && <span>· {data.campaign_name}</span>}
          </div>
        </div>
        {can("content.edit") && EDITABLE.has(data.status) && (
          <Button variant="secondary" onClick={() => setRegenerating(true)}>
            Regenerate with AI
          </Button>
        )}
      </header>

      <div className="grid gap-6 xl:grid-cols-[1fr_22rem]">
        <div className="flex min-w-0 flex-col gap-6">
          <Card>
            <VersionEditor item={data} />
          </Card>
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
    </>
  );
}
