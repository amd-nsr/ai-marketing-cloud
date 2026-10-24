"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { MockAIBadge } from "@/components/features/ai-badges";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Select, Textarea } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { useOrg } from "@/hooks/use-org";
import { useWorkflowRun } from "@/hooks/use-workflow-run";
import { Input } from "@/components/ui/input";
import {
  type ContentFormat,
  type ContentPlatform,
  type CreativeDirection,
  generateContent,
  listCampaigns,
} from "@/lib/api/content";
import { errorMessage } from "@/lib/api/errors";
import { cn } from "@/lib/utils";
import { useAudiences, useBusinessProfile } from "@/features/brand/queries";

import { LANGUAGES } from "./studio/writing-assistant";

import { FORMAT_LABEL, PLATFORM_FORMATS, PLATFORM_LABEL } from "./labels";

type Target = `${ContentPlatform}:${ContentFormat}`;
const DEFAULT_FORMAT: Record<ContentPlatform, ContentFormat> = {
  instagram: "post",
  facebook: "post",
  tiktok: "short_video",
  blog: "article",
  email: "newsletter",
};

/** Mounted only while open, so every generation starts from fresh state. */
export function GenerateContentDialog({
  onClose,
  onGenerated,
  defaultCampaign,
  defaultTargets,
}: {
  onClose: () => void;
  onGenerated: (itemIds: string[]) => void;
  defaultCampaign?: string;
  /** Preselected targets, e.g. a campaign's platforms. */
  defaultTargets?: Target[];
}) {
  const { organization } = useOrg();
  const queryClient = useQueryClient();
  const profile = useBusinessProfile();
  const campaigns = useQuery({
    queryKey: ["orgs", organization.id, "campaigns", "open"],
    queryFn: () => listCampaigns(organization.id, "planned,active"),
  });
  const preferred = profile.data?.preferred_platforms ?? [];
  const [brief, setBrief] = useState("");
  const [campaign, setCampaign] = useState(defaultCampaign ?? "");
  const [targets, setTargets] = useState<Target[] | null>(defaultTargets ?? null);
  const audiences = useAudiences();
  const [direction, setDirection] = useState<CreativeDirection>({ length: "" });
  const [showDirection, setShowDirection] = useState(false);
  const [runId, setRunId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const run = useWorkflowRun(organization.id, runId);

  const selected: Target[] = targets ?? preferred.map((p) => `${p}:${DEFAULT_FORMAT[p]}` as Target);
  const toggle = (t: Target) =>
    setTargets(selected.includes(t) ? selected.filter((x) => x !== t) : [...selected, t]);

  useEffect(() => {
    if (run.data?.status === "succeeded") {
      void queryClient.invalidateQueries({ queryKey: ["orgs", organization.id, "content"] });
      const ids = (run.data.output.item_ids as string[] | undefined) ?? [];
      onGenerated(ids);
    }
  }, [run.data, organization.id, queryClient, onGenerated]);

  const start = async () => {
    setError(null);
    if (brief.trim().length < 5) return setError("Describe what the content should be about.");
    if (!selected.length) return setError("Choose at least one platform and format.");
    setStarting(true);
    try {
      const created = await generateContent(organization.id, {
        brief: brief.trim(),
        targets: selected.map((t) => {
          const [platform, format] = t.split(":");
          return { platform, format };
        }),
        campaign: campaign || null,
        ...direction,
        audience: direction.audience || null,
      });
      setRunId(created.id);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setStarting(false);
    }
  };

  const working = starting || (runId !== null && run.data?.status !== "failed");

  return (
    <Dialog
      open
      onClose={() => !working && onClose()}
      title="Generate content with AI"
      description="One draft per platform and format, written in your brand voice. Every draft stays editable and needs approval before publishing."
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={working}>
            Close
          </Button>
          <Button onClick={start} disabled={working}>
            {working
              ? "Generating…"
              : run.data?.status === "failed"
                ? "Try again"
                : "Generate drafts"}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <Field
          label="What's it about?"
          hint="e.g. 'Announce our new oat-milk flat white, available from Monday'."
        >
          {(p) => (
            <Textarea
              rows={3}
              maxLength={2000}
              value={brief}
              onChange={(e) => setBrief(e.target.value)}
              disabled={working}
              {...p}
            />
          )}
        </Field>
        <fieldset disabled={working}>
          <legend className="mb-2 text-sm font-medium">Platforms and formats</legend>
          <div className="flex flex-col gap-2">
            {(Object.keys(PLATFORM_FORMATS) as ContentPlatform[]).map((platform) => (
              <div key={platform} className="flex flex-wrap items-center gap-2">
                <span className="w-24 text-sm">{PLATFORM_LABEL[platform]}</span>
                {PLATFORM_FORMATS[platform].map((format) => {
                  const t = `${platform}:${format}` as Target;
                  const on = selected.includes(t);
                  return (
                    <button
                      key={t}
                      type="button"
                      aria-pressed={on}
                      onClick={() => toggle(t)}
                      className={cn(
                        "rounded-full border px-3 py-1 text-xs",
                        on
                          ? "border-primary bg-primary text-primary-foreground"
                          : "border-border hover:bg-neutral-soft",
                      )}
                    >
                      {FORMAT_LABEL[format]}
                    </button>
                  );
                })}
              </div>
            ))}
          </div>
        </fieldset>
        <div>
          <button
            type="button"
            className="text-sm font-medium text-primary hover:underline"
            aria-expanded={showDirection}
            onClick={() => setShowDirection((s) => !s)}
          >
            {showDirection
              ? "− Hide creative direction"
              : "+ Objective, audience, tone, language, length"}
          </button>
        </div>
        {showDirection && (
          <fieldset disabled={working} className="grid gap-3 sm:grid-cols-2">
            <Field label="Objective" optional>
              {(p) => (
                <Input
                  value={direction.objective ?? ""}
                  maxLength={200}
                  placeholder="e.g. more weekday visits"
                  onChange={(e) => setDirection({ ...direction, objective: e.target.value })}
                  {...p}
                />
              )}
            </Field>
            <Field label="Audience" optional>
              {(p) => (
                <Select
                  value={direction.audience ?? ""}
                  onChange={(e) => setDirection({ ...direction, audience: e.target.value })}
                  {...p}
                >
                  <option value="">Your usual audience</option>
                  {audiences.data?.results.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
            <Field label="Tone" optional hint="Defaults to your brand voice.">
              {(p) => (
                <Input
                  value={direction.tone ?? ""}
                  maxLength={100}
                  placeholder="e.g. playful"
                  onChange={(e) => setDirection({ ...direction, tone: e.target.value })}
                  {...p}
                />
              )}
            </Field>
            <Field label="Language" optional>
              {(p) => (
                <Select
                  value={direction.language ?? ""}
                  onChange={(e) => setDirection({ ...direction, language: e.target.value })}
                  {...p}
                >
                  <option value="">Your content language</option>
                  {LANGUAGES.map((l) => (
                    <option key={l}>{l}</option>
                  ))}
                </Select>
              )}
            </Field>
            <Field label="Length" optional>
              {(p) => (
                <Select
                  value={direction.length ?? ""}
                  onChange={(e) =>
                    setDirection({
                      ...direction,
                      length: e.target.value as CreativeDirection["length"],
                    })
                  }
                  {...p}
                >
                  <option value="">Platform default</option>
                  <option value="short">Short</option>
                  <option value="medium">Medium</option>
                  <option value="long">Long</option>
                </Select>
              )}
            </Field>
          </fieldset>
        )}
        {campaigns.data && campaigns.data.count > 0 && (
          <Field label="Campaign" optional>
            {(p) => (
              <Select
                value={campaign}
                onChange={(e) => setCampaign(e.target.value)}
                disabled={working}
                {...p}
              >
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
        {working && (
          <div className="flex items-center gap-2 text-sm text-muted" aria-live="polite">
            <Spinner />
            {run.data?.status === "running" ? "Writing drafts…" : "Queued…"}
            {run.data && <MockAIBadge isMock={run.data.is_mock} />}
          </div>
        )}
        {error && <Alert tone="danger">{error}</Alert>}
        {run.data?.status === "failed" && (
          <Alert tone="danger" title="Generation failed">
            {run.data.error_message || "Please try again."}
          </Alert>
        )}
      </div>
    </Dialog>
  );
}
