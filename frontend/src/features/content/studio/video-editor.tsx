"use client";

import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { MockAIBadge } from "@/components/features/ai-badges";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input, Select } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { useToast } from "@/components/ui/toast";
import { useOrg } from "@/hooks/use-org";
import { useWorkflowRun } from "@/hooks/use-workflow-run";
import {
  type ContentItem,
  createVersion,
  getRenderJob,
  listRenderJobs,
  renderVideo,
  requestStoryboard,
  type Storyboard,
} from "@/lib/api/content";
import { errorMessage } from "@/lib/api/errors";
import { cn } from "@/lib/utils";

import { useAssets, useRefreshItem } from "../editor/queries";
import { ColorField } from "./color-field";
import {
  assetUrl,
  blankVideo,
  type Clip,
  clipStarts,
  MAX_VIDEO_SECONDS,
  readDocument,
  type Subtitle,
  uid,
  VIDEO_SIZES,
  type VideoDocument,
  videoDuration,
} from "./document";
import { AssetPickerDialog, type PickedAsset } from "./library-browser";
import { useBrandPalette, useLibrary, useStudioCapabilities } from "./queries";
import { useHistory } from "./use-history";

const EDITABLE = new Set(["draft", "in_review", "changes_requested", "approved"]);
const RENDERABLE = new Set(["draft", "changes_requested"]);
const round = (n: number) => Math.round(n * 10) / 10;

function NumberInput({
  label,
  value,
  onChange,
  min,
  max,
  step = 0.1,
  disabled,
}: {
  label: string;
  value: number;
  onChange: (n: number) => void;
  min: number;
  max: number;
  step?: number;
  disabled?: boolean;
}) {
  return (
    <label className="flex flex-col gap-1 text-xs font-medium">
      {label}
      <Input
        type="number"
        className="h-8"
        value={round(value)}
        min={min}
        max={max}
        step={step}
        disabled={disabled}
        onChange={(e) => {
          const n = Number(e.target.value);
          if (Number.isFinite(n)) onChange(Math.min(max, Math.max(min, n)));
        }}
      />
    </label>
  );
}

// --- Preview and timeline ---------------------------------------------------------

/** Position on the timeline strip (0..1), laid out by clip durations. */
function stripFraction(doc: VideoDocument, starts: number[], t: number): number {
  const sum = doc.clips.reduce((n, c) => n + c.duration, 0);
  if (!sum) return 0;
  const i = Math.max(
    0,
    starts.findLastIndex((s) => s <= t + 1e-6),
  );
  const before = doc.clips.slice(0, i).reduce((n, c) => n + c.duration, 0);
  const local = Math.min(Math.max(t - (starts[i] ?? 0), 0), doc.clips[i]?.duration ?? 0);
  return (before + local) / sum;
}

/** Inverse of ``stripFraction``: the output time at a point of the strip. */
function timeAtFraction(doc: VideoDocument, starts: number[], f: number): number {
  const sum = doc.clips.reduce((n, c) => n + c.duration, 0);
  let x = f * sum;
  for (const [i, c] of doc.clips.entries()) {
    if (x <= c.duration) return (starts[i] ?? 0) + x;
    x -= c.duration;
  }
  return videoDuration(doc);
}

function usePlayback(total: number) {
  const [t, setT] = useState(0);
  const [playing, setPlaying] = useState(false);
  useEffect(() => {
    if (!playing) return;
    let frame = 0;
    let last = performance.now();
    const tick = (now: number) => {
      setT((prev) => {
        const next = prev + (now - last) / 1000;
        if (next >= total) {
          setPlaying(false);
          return total;
        }
        return next;
      });
      last = now;
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [playing, total]);
  return { t: Math.min(t, total), setT, playing, setPlaying };
}

/**
 * Approximate in-browser preview (cuts, overlays, subtitles). The rendered MP4 is the
 * exact output; this exists so edits can be checked without waiting for a render.
 */
function PreviewScreen({
  doc,
  orgId,
  kinds,
  t,
  playing,
}: {
  doc: VideoDocument;
  orgId: string;
  kinds: Map<string, string>;
  t: number;
  playing: boolean;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const starts = useMemo(() => clipStarts(doc), [doc]);
  const index = Math.max(
    0,
    starts.findLastIndex((s) => s <= t + 1e-6),
  );
  const clip = doc.clips[index];
  const local = clip ? t - starts[index] : 0;
  const kind = clip ? kinds.get(clip.asset.id) : undefined;
  const subtitle = doc.subtitles.find((s) => t >= s.start && t < s.end);
  const fadingOut =
    clip?.transition === "fade" &&
    index < doc.clips.length - 1 &&
    local > clip.duration - clip.transition_duration;

  useEffect(() => {
    const v = videoRef.current;
    if (!v || !clip || kind !== "video") return;
    const target = clip.trim_start + local;
    if (Math.abs(v.currentTime - target) > 0.3) v.currentTime = target;
    if (playing && v.paused) void v.play().catch(() => undefined);
    if (!playing && !v.paused) v.pause();
  }, [clip, kind, local, playing]);

  const overlayPos = {
    top: "top-[8%]",
    center: "top-1/2 -translate-y-1/2",
    bottom: "bottom-[14%]",
  };
  const previewWidth = doc.height > doc.width ? 240 : 420;
  return (
    <div
      className="relative mx-auto w-full overflow-hidden rounded-lg bg-black shadow-md"
      style={{ aspectRatio: `${doc.width} / ${doc.height}`, maxWidth: previewWidth }}
    >
      <div className={cn("absolute inset-0 transition-opacity", fadingOut && "opacity-60")}>
        {clip && kind === "video" && (
          <video
            ref={videoRef}
            key={clip.id}
            src={assetUrl(orgId, clip.asset)}
            muted
            playsInline
            className="absolute inset-0 size-full object-cover"
          />
        )}
        {clip && kind !== "video" && (
          // eslint-disable-next-line @next/next/no-img-element -- authenticated same-origin file
          <img
            key={clip.id}
            src={assetUrl(orgId, clip.asset)}
            alt=""
            className="absolute inset-0 size-full object-cover"
          />
        )}
      </div>
      {!clip && (
        <p className="absolute inset-0 flex items-center justify-center p-4 text-center text-xs text-white/70">
          Add clips to the timeline to preview
        </p>
      )}
      {clip?.overlay && (
        <p
          className={cn(
            "absolute inset-x-3 text-center font-bold break-words",
            overlayPos[clip.overlay.position],
            clip.overlay.background && "rounded bg-black/45 px-2 py-1",
          )}
          style={{
            color: clip.overlay.color,
            fontSize: `${(clip.overlay.font_size / doc.width) * previewWidth}px`,
          }}
        >
          {clip.overlay.text}
        </p>
      )}
      {subtitle && (
        <p className="absolute inset-x-3 bottom-[20%] rounded bg-black/45 px-2 py-1 text-center text-xs text-white">
          {subtitle.text}
        </p>
      )}
      <span className="absolute top-2 left-2 rounded bg-black/50 px-1.5 text-[10px] text-white/80">
        Preview
      </span>
    </div>
  );
}

function Timeline({
  doc,
  orgId,
  meta,
  t,
  selectedId,
  onSeek,
  onSelect,
}: {
  doc: VideoDocument;
  orgId: string;
  meta: Map<string, { kind: string; duration: number | null; title: string }>;
  t: number;
  selectedId: string | null;
  onSeek: (t: number) => void;
  onSelect: (id: string) => void;
}) {
  const starts = useMemo(() => clipStarts(doc), [doc]);
  const strip = useRef<HTMLDivElement>(null);
  const sum = doc.clips.reduce((n, c) => n + c.duration, 0);
  const total = videoDuration(doc);
  const ticks = Array.from({ length: Math.floor(total / 5) + 1 }, (_, i) => i * 5);

  if (!doc.clips.length)
    return (
      <p className="rounded-md border border-dashed border-border p-6 text-center text-sm text-muted">
        The timeline is empty. Add photos or video clips from your media library.
      </p>
    );

  const seekFromEvent = (clientX: number) => {
    const rect = strip.current?.getBoundingClientRect();
    if (!rect) return;
    const f = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width));
    onSeek(timeAtFraction(doc, starts, f));
  };

  return (
    <div className="flex flex-col gap-1">
      <div className="relative h-4 text-[10px] text-muted" aria-hidden>
        {ticks.map((s) => (
          <span
            key={s}
            className="absolute -translate-x-1/2"
            style={{ left: `${stripFraction(doc, starts, s) * 100}%` }}
          >
            {s}s
          </span>
        ))}
      </div>
      <div
        ref={strip}
        className="relative flex h-20 w-full cursor-pointer overflow-hidden rounded-md bg-neutral-900"
        onClick={(e) => seekFromEvent(e.clientX)}
        role="slider"
        tabIndex={0}
        aria-label="Timeline position"
        aria-valuemin={0}
        aria-valuemax={round(total)}
        aria-valuenow={round(t)}
        onKeyDown={(e) => {
          if (e.key === "ArrowRight") onSeek(Math.min(total, t + 0.5));
          if (e.key === "ArrowLeft") onSeek(Math.max(0, t - 0.5));
        }}
      >
        {doc.clips.map((c, i) => {
          const info = meta.get(c.asset.id);
          const url = assetUrl(orgId, c.asset);
          return (
            <button
              key={c.id}
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onSelect(c.id);
                seekFromEvent(e.clientX);
              }}
              aria-label={`Clip ${i + 1}, ${c.duration} seconds${c.overlay ? `, text: ${c.overlay.text}` : ""}`}
              aria-pressed={selectedId === c.id}
              className={cn(
                "relative h-full shrink-0 overflow-hidden border-r-2 border-neutral-900 text-left",
                selectedId === c.id && "ring-2 ring-primary ring-inset",
              )}
              style={{ width: `${(c.duration / sum) * 100}%` }}
            >
              {info?.kind === "video" ? (
                <video
                  src={`${url}#t=${c.trim_start + 0.1}`}
                  muted
                  preload="metadata"
                  className="absolute inset-0 size-full object-cover opacity-80"
                />
              ) : (
                // eslint-disable-next-line @next/next/no-img-element -- authenticated same-origin file
                <img
                  src={url}
                  alt=""
                  className="absolute inset-0 size-full object-cover opacity-80"
                />
              )}
              <span className="absolute top-1 left-1 rounded bg-black/60 px-1 text-[10px] text-white">
                {i + 1} · {c.duration}s
              </span>
              {c.overlay && (
                <span className="absolute bottom-1 left-1 max-w-[90%] truncate rounded bg-black/60 px-1 text-[10px] text-white">
                  T: {c.overlay.text}
                </span>
              )}
              {c.transition === "fade" && i < doc.clips.length - 1 && (
                <span className="absolute top-1 right-1 rounded bg-primary px-1 text-[10px] text-primary-foreground">
                  fade
                </span>
              )}
            </button>
          );
        })}
        <span
          aria-hidden
          className="pointer-events-none absolute inset-y-0 w-0.5 bg-white shadow"
          style={{ left: `${stripFraction(doc, starts, t) * 100}%` }}
        />
      </div>
      {doc.subtitles.length > 0 && (
        <div
          className="relative h-3 w-full overflow-hidden rounded bg-neutral-soft"
          aria-label="Captions track"
        >
          {doc.subtitles.map((s, i) => {
            const a = stripFraction(doc, starts, s.start);
            const b = stripFraction(doc, starts, Math.min(s.end, total));
            return (
              <span
                key={i}
                title={s.text}
                className="absolute inset-y-0 rounded bg-info/60"
                style={{ left: `${a * 100}%`, width: `${Math.max(b - a, 0.005) * 100}%` }}
              />
            );
          })}
        </div>
      )}
      {doc.audio.map((a, i) => (
        <div
          key={i}
          className="relative h-3 w-full overflow-hidden rounded bg-neutral-soft"
          aria-label={`${a.role} track`}
          title={`${a.role} · ${meta.get(a.asset.id)?.title ?? "Audio"}`}
        >
          <span
            className="absolute inset-y-0 right-0 rounded bg-success/60"
            style={{ left: `${stripFraction(doc, starts, a.start) * 100}%` }}
          />
        </div>
      ))}
    </div>
  );
}

// --- Storyboard -------------------------------------------------------------------

function StoryboardPanel({
  item,
  onApplySubtitles,
  onAddScene,
  editable,
}: {
  item: ContentItem;
  onApplySubtitles: (sb: Storyboard) => void;
  onAddScene: (scene: Storyboard["scenes"][number]) => void;
  editable: boolean;
}) {
  const { organization } = useOrg();
  const toast = useToast();
  const refresh = useRefreshItem();
  const caps = useStudioCapabilities();
  const [runId, setRunId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const run = useWorkflowRun(organization.id, runId);
  const storyboard =
    run.data?.status === "succeeded" ? (run.data.output as unknown as Storyboard) : null;
  const working = runId !== null && !run.data?.status.match(/succeeded|failed|cancelled/);

  const start = async () => {
    setError(null);
    try {
      setRunId((await requestStoryboard(organization.id, item.id)).id);
    } catch (e) {
      setError(errorMessage(e));
    }
  };
  const saveScript = async (sb: Storyboard) => {
    const script = sb.scenes
      .map(
        (s, i) =>
          `${i + 1}. (${s.duration_seconds}s) ${s.description}` +
          (s.on_screen_text ? `\n   On screen: ${s.on_screen_text}` : "") +
          (s.voiceover ? `\n   Voiceover: ${s.voiceover}` : ""),
      )
      .join("\n");
    try {
      await createVersion(organization.id, item.id, { script: `Hook: ${sb.hook}\n\n${script}` });
      await refresh();
      toast("Storyboard saved as the video script.");
    } catch (e) {
      toast(errorMessage(e), "danger");
    }
  };

  return (
    <Card>
      <CardHeader
        title="Storyboard"
        description="Plan scenes with AI from your brief and business context, then add your own media for each."
        actions={
          editable &&
          caps.data?.text_generation.available && (
            <Button size="sm" variant="secondary" onClick={start} disabled={working}>
              {working ? "Planning…" : storyboard ? "Plan again" : "Plan with AI"}
            </Button>
          )
        }
      />
      {error && <Alert tone="danger">{error}</Alert>}
      {run.data?.status === "failed" && <Alert tone="danger">{run.data.error_message}</Alert>}
      {working && <Spinner />}
      {storyboard && (
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm font-medium">{storyboard.title}</p>
            <MockAIBadge isMock={Boolean(run.data?.is_mock)} />
          </div>
          <p className="text-sm">
            <span className="font-medium">Hook:</span> {storyboard.hook}
          </p>
          <ol className="flex flex-col gap-2">
            {storyboard.scenes.map((s, i) => (
              <li
                key={i}
                className="flex items-start justify-between gap-3 rounded-md border border-border p-3 text-sm"
              >
                <div>
                  <p className="font-medium">
                    {i + 1}. {s.description}{" "}
                    <span className="text-muted">· {s.duration_seconds}s</span>
                  </p>
                  {s.on_screen_text && <p className="text-muted">On screen: {s.on_screen_text}</p>}
                  {s.voiceover && <p className="text-muted">Voiceover: {s.voiceover}</p>}
                </div>
                {editable && (
                  <Button size="sm" variant="secondary" onClick={() => onAddScene(s)}>
                    Add media
                  </Button>
                )}
              </li>
            ))}
          </ol>
          {editable && (
            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant="secondary" onClick={() => onApplySubtitles(storyboard)}>
                Use on-screen text as subtitles
              </Button>
              <Button size="sm" variant="ghost" onClick={() => void saveScript(storyboard)}>
                Save as video script
              </Button>
            </div>
          )}
        </div>
      )}
      {!storyboard && !working && (
        <p className="text-sm text-muted">
          {caps.data?.ai_video_generation.note ?? "Videos are edited from your own clips."}
        </p>
      )}
    </Card>
  );
}

// --- Render status ----------------------------------------------------------------

function RenderPanel({
  item,
  dirty,
  onSave,
  disabledReason,
}: {
  item: ContentItem;
  dirty: boolean;
  onSave: () => Promise<boolean>;
  disabledReason: string | null;
}) {
  const { organization, can } = useOrg();
  const refresh = useRefreshItem();
  const caps = useStudioCapabilities();
  const assets = useAssets(item.id);
  const [jobId, setJobId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const jobs = useQuery({
    queryKey: ["orgs", organization.id, "content", item.id, "render-jobs"],
    queryFn: () => listRenderJobs(organization.id, item.id),
  });
  const activeId =
    jobId ?? jobs.data?.find((j) => j.status === "queued" || j.status === "running")?.id ?? null;
  const job = useQuery({
    queryKey: ["orgs", organization.id, "render-job", activeId],
    queryFn: () => getRenderJob(organization.id, activeId as string),
    enabled: Boolean(activeId),
    refetchInterval: (q) =>
      q.state.data && ["succeeded", "failed"].includes(q.state.data.status) ? false : 2000,
  });
  const latest = job.data ?? jobs.data?.[0];
  const rendering = latest?.status === "queued" || latest?.status === "running";
  const output = assets.data?.find(
    (a) => a.source === "render" && a.content_type.startsWith("video/"),
  );
  const checks = item.current_version?.checks ?? [];
  const stale = checks.some((c) => c.code === "render_stale");

  useEffect(() => {
    if (job.data?.status === "succeeded" || job.data?.status === "failed") {
      void refresh();
      void jobs.refetch();
    }
  }, [job.data?.status]); // eslint-disable-line react-hooks/exhaustive-deps

  const start = async () => {
    setError(null);
    if (dirty && !(await onSave())) return;
    try {
      const created = await renderVideo(organization.id, item.id);
      setJobId(created.id);
    } catch (e) {
      setError(errorMessage(e));
    }
  };

  const unavailable = caps.data && !caps.data.video_rendering.available;
  return (
    <Card>
      <CardHeader
        title="Render"
        description="Renders an MP4 (H.264) in the background and attaches it for approval and publishing."
        actions={
          can("content.edit") && (
            <Button
              size="sm"
              onClick={() => void start()}
              disabled={rendering || Boolean(unavailable) || Boolean(disabledReason)}
            >
              {rendering
                ? "Rendering…"
                : latest?.status === "failed"
                  ? "Retry render"
                  : dirty
                    ? "Save and render"
                    : output
                      ? "Render again"
                      : "Render video"}
            </Button>
          )
        }
      />
      {unavailable && <Alert tone="warning">{caps.data?.video_rendering.note}</Alert>}
      {disabledReason && <p className="text-xs text-muted">{disabledReason}</p>}
      {error && <Alert tone="danger">{error}</Alert>}
      {latest && (
        <p className="mb-2 flex flex-wrap items-center gap-2 text-sm">
          <Badge
            tone={
              latest.status === "succeeded"
                ? "success"
                : latest.status === "failed"
                  ? "danger"
                  : "info"
            }
          >
            {latest.status === "queued"
              ? "Queued"
              : latest.status === "running"
                ? "Rendering"
                : latest.status === "succeeded"
                  ? "Rendered"
                  : "Failed"}
          </Badge>
          <span className="text-muted">
            Version {latest.version_number}
            {latest.attempts > 1 ? ` · attempt ${latest.attempts}` : ""}
          </span>
          {rendering && <Spinner />}
        </p>
      )}
      {latest?.status === "failed" && <Alert tone="danger">{latest.error_message}</Alert>}
      {stale && output && (
        <Alert tone="warning" className="mb-2">
          The project changed after this render. Render again before submitting.
        </Alert>
      )}
      {output ? (
        <div className="flex flex-col gap-2">
          <video
            src={output.file_url}
            controls
            playsInline
            className="mx-auto max-h-[420px] w-auto rounded-md bg-black"
          />
          <a
            href={output.file_url}
            download={output.original_filename || "video.mp4"}
            className="text-sm text-primary hover:underline"
          >
            Download MP4 · {output.duration_seconds?.toFixed(1)}s ·{" "}
            {(output.size_bytes / 1024 / 1024).toFixed(1)} MB
          </a>
        </div>
      ) : (
        !rendering && <p className="text-sm text-muted">Not rendered yet.</p>
      )}
    </Card>
  );
}

// --- Editor -----------------------------------------------------------------------

export function VideoEditor({ item }: { item: ContentItem }) {
  const { organization, can } = useOrg();
  const toast = useToast();
  const refresh = useRefreshItem();
  const palette = useBrandPalette();
  const caps = useStudioCapabilities();
  const media = useLibrary({ kind: "image,video,audio" });
  const saved = useMemo(() => {
    const d = readDocument(item.current_version?.document);
    return d?.kind === "video" ? d : null;
  }, [item.current_version?.document]);
  const history = useHistory<VideoDocument | null>(saved);
  const doc = history.value;
  const [picker, setPicker] = useState<null | {
    mode: "clip" | "audio" | "cover" | "replace";
    scene?: Storyboard["scenes"][number];
  }>(null);
  const [size, setSize] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [selectedClipId, setSelectedClipId] = useState<string | null>(null);
  const playback = usePlayback(doc ? videoDuration(doc) : 0);

  const editable = can("content.edit") && EDITABLE.has(item.status);
  const dirty = JSON.stringify(doc) !== JSON.stringify(saved);
  const meta = useMemo(() => {
    const m = new Map<string, { kind: string; duration: number | null; title: string }>();
    for (const a of media.data?.results ?? [])
      m.set(a.id, { kind: a.kind, duration: a.duration_seconds, title: a.title });
    return m;
  }, [media.data]);
  const kinds = useMemo(() => new Map([...meta].map(([id, v]) => [id, v.kind])), [meta]);

  const savedKey = item.current_version?.id;
  const lastSaved = useRef(savedKey);
  useEffect(() => {
    if (lastSaved.current !== savedKey) {
      lastSaved.current = savedKey;
      history.reset(saved);
    }
  }, [savedKey, saved, history]);

  const set = useCallback((next: VideoDocument, key?: string) => history.set(next, key), [history]);
  const updateClip = (id: string, patch: Partial<Clip>, key?: string) =>
    doc &&
    set({ ...doc, clips: doc.clips.map((c) => (c.id === id ? { ...c, ...patch } : c)) }, key);
  const moveClip = (i: number, delta: number) => {
    if (!doc) return;
    const j = i + delta;
    if (j < 0 || j >= doc.clips.length) return;
    const clips = [...doc.clips];
    [clips[i], clips[j]] = [clips[j], clips[i]];
    set({ ...doc, clips });
  };
  const updateSubtitle = (i: number, patch: Partial<Subtitle>, key?: string) =>
    doc &&
    set(
      { ...doc, subtitles: doc.subtitles.map((s, k) => (k === i ? { ...s, ...patch } : s)) },
      key,
    );

  const onPicked = (asset: PickedAsset) => {
    if (!doc || !picker) return;
    if (picker.mode === "audio") {
      set({
        ...doc,
        audio: [
          ...doc.audio,
          {
            asset: asset.ref,
            role: doc.audio.length ? ("voiceover" as const) : ("music" as const),
            volume: 0.8,
            start: 0,
          },
        ].slice(0, 2),
      });
      setPicker(null);
      return;
    }
    if (picker.mode === "cover") {
      set({ ...doc, cover: asset.ref });
      setPicker(null);
      return;
    }
    if (picker.mode === "replace" && selectedClipId) {
      updateClip(selectedClipId, { asset: asset.ref, trim_start: 0 });
      setPicker(null);
      return;
    }
    const scene = picker.scene;
    const duration = scene
      ? Math.min(Math.max(scene.duration_seconds, 1), 15)
      : asset.kind === "video"
        ? Math.min(asset.duration ?? 5, 6)
        : 3;
    const clip: Clip = {
      id: uid("c"),
      asset: asset.ref,
      trim_start: 0,
      duration: round(Math.max(0.5, duration)),
      overlay: scene?.on_screen_text
        ? {
            text: scene.on_screen_text.slice(0, 200),
            position: "bottom",
            color: "#ffffff",
            font_size: Math.round(doc.width / 18),
            background: true,
          }
        : null,
      transition: "none",
      transition_duration: 0.5,
    };
    set({ ...doc, clips: [...doc.clips, clip].slice(0, 30) });
    setSelectedClipId(clip.id);
    setPicker(null);
  };

  const applySubtitles = (sb: Storyboard) => {
    if (!doc) return;
    let t = 0;
    const subs: Subtitle[] = [];
    for (const s of sb.scenes) {
      const text = s.voiceover || s.on_screen_text;
      if (text)
        subs.push({
          start: round(t),
          end: round(Math.min(t + s.duration_seconds, MAX_VIDEO_SECONDS)),
          text: text.slice(0, 300),
        });
      t += s.duration_seconds;
    }
    set({ ...doc, subtitles: subs.slice(0, 200) });
    toast(`${subs.length} subtitles added. Adjust timings after adding clips.`);
  };

  const save = async (): Promise<boolean> => {
    if (!doc) return false;
    setSaving(true);
    setError(null);
    try {
      const v = await createVersion(organization.id, item.id, {
        document: doc as unknown as Record<string, unknown>,
      });
      await refresh();
      toast(`Video project saved as version ${v.number}.`);
      return true;
    } catch (e) {
      setError(errorMessage(e));
      return false;
    } finally {
      setSaving(false);
    }
  };

  if (!doc) {
    if (!editable)
      return (
        <Card>
          <p className="text-sm text-muted">No video project yet.</p>
        </Card>
      );
    return (
      <Card>
        <CardHeader
          title="Start a video project"
          description="Build a short marketing video from your own photos and clips: trim, order, add text, subtitles, and music, then render it."
        />
        <div className="flex flex-wrap items-end gap-2">
          <Field label="Format" className="w-full sm:w-80">
            {(p) => (
              <Select value={size} onChange={(e) => setSize(Number(e.target.value))} {...p}>
                {VIDEO_SIZES.map((s, i) => (
                  <option key={s.label} value={i}>
                    {s.label} — {s.width}×{s.height}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Button
            onClick={() =>
              history.set(blankVideo(VIDEO_SIZES[size].width, VIDEO_SIZES[size].height))
            }
          >
            Create project
          </Button>
        </div>
        {caps.data && (
          <p className="mt-3 text-xs text-muted">
            {caps.data.ai_video_generation.note} {caps.data.ai_voiceover.note}
          </p>
        )}
      </Card>
    );
  }

  const total = videoDuration(doc);
  const starts = clipStarts(doc);
  const renderBlocked = !RENDERABLE.has(item.status)
    ? "Rendering is locked while content is in review or approved. Saving changes returns it to draft."
    : doc.clips.length === 0
      ? "Add at least one clip to render."
      : null;
  const playingIndex = Math.max(
    0,
    starts.findLastIndex((s) => s <= playback.t + 1e-6),
  );
  const selectedIndex = doc.clips.findIndex((c) => c.id === selectedClipId);
  const selectedClip = selectedIndex >= 0 ? doc.clips[selectedIndex] : null;
  const info = selectedClip ? meta.get(selectedClip.asset.id) : undefined;
  const isVideo = info?.kind === "video";
  const maxTrim = isVideo && info?.duration ? Math.max(0, info.duration - 0.5) : 0;

  const splitAtPlayhead = () => {
    const i = playingIndex;
    const c = doc.clips[i];
    if (!c) return;
    const local = round(playback.t - starts[i]);
    if (local < 0.5 || c.duration - local < 0.5)
      return toast("Move the playhead at least 0.5s inside a clip to split it.", "danger");
    const second: Clip = {
      ...c,
      id: uid("c"),
      trim_start: kinds.get(c.asset.id) === "video" ? round(c.trim_start + local) : 0,
      duration: round(c.duration - local),
    };
    const first: Clip = { ...c, duration: local, transition: "none" };
    set({ ...doc, clips: [...doc.clips.slice(0, i), first, second, ...doc.clips.slice(i + 1)] });
    setSelectedClipId(second.id);
  };
  const removeClip = (id: string) => {
    set({ ...doc, clips: doc.clips.filter((x) => x.id !== id) });
    if (selectedClipId === id) setSelectedClipId(null);
  };

  return (
    <div className="flex flex-col gap-6">
      <Card className="p-3 sm:p-4">
        {/* Top bar */}
        <div className="mb-3 flex flex-wrap items-center gap-2">
          {editable && (
            <>
              <Button size="sm" variant="ghost" disabled={!history.canUndo} onClick={history.undo}>
                ↶ Undo
              </Button>
              <Button size="sm" variant="ghost" disabled={!history.canRedo} onClick={history.redo}>
                ↷ Redo
              </Button>
            </>
          )}
          <span className="text-xs text-muted">
            {doc.clips.length} clip{doc.clips.length === 1 ? "" : "s"} · {round(total)}s of{" "}
            {MAX_VIDEO_SECONDS}s · {doc.width}×{doc.height} @ {doc.fps}fps
          </span>
          {editable && (
            <div className="ml-auto flex flex-wrap items-center gap-2">
              {dirty ? <Badge tone="warning">Unsaved changes</Badge> : <Badge>Saved</Badge>}
              {dirty && saved && (
                <Button size="sm" variant="ghost" onClick={() => history.reset(saved)}>
                  Discard
                </Button>
              )}
              <Button size="sm" disabled={!dirty || saving} onClick={() => void save()}>
                {saving ? "Saving…" : "Save project"}
              </Button>
            </div>
          )}
        </div>
        {error && (
          <Alert tone="danger" className="mb-3">
            {error}
          </Alert>
        )}
        {total > MAX_VIDEO_SECONDS && (
          <Alert tone="danger" className="mb-3">
            The video is longer than {MAX_VIDEO_SECONDS} seconds. Shorten some clips.
          </Alert>
        )}

        <div className="grid gap-4 lg:grid-cols-[17rem_1fr_17rem]">
          {/* Captions */}
          <section
            aria-label="Captions"
            className="order-2 flex min-w-0 flex-col gap-2 lg:order-none"
          >
            <div className="flex items-center justify-between gap-2">
              <h3 className="text-sm font-semibold">Captions</h3>
              {editable && (
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={doc.subtitles.length >= 200}
                  onClick={() => {
                    const start = round(playback.t);
                    const subtitles = [
                      ...doc.subtitles,
                      {
                        start,
                        end: round(Math.min(start + 2, MAX_VIDEO_SECONDS)),
                        text: "Caption",
                      },
                    ].sort((a, b) => a.start - b.start);
                    set({ ...doc, subtitles });
                  }}
                >
                  + At {round(playback.t).toFixed(1)}s
                </Button>
              )}
            </div>
            <p className="text-xs text-muted">
              Burned into the video. Use the storyboard to draft them.
            </p>
            <ol className="flex max-h-[26rem] flex-col gap-2 overflow-y-auto pr-1">
              {doc.subtitles.length === 0 && (
                <li className="text-sm text-muted">No captions yet.</li>
              )}
              {doc.subtitles.map((s, i) => {
                const active = playback.t >= s.start && playback.t < s.end;
                return (
                  <li
                    key={i}
                    className={cn(
                      "flex flex-col gap-1 rounded-md border p-2",
                      active ? "border-primary bg-neutral-soft" : "border-border",
                    )}
                  >
                    <div className="flex items-center gap-1">
                      <button
                        type="button"
                        className="font-mono text-xs text-primary hover:underline"
                        onClick={() => playback.setT(s.start)}
                        aria-label={`Jump to caption ${i + 1}`}
                      >
                        {s.start.toFixed(1)}s
                      </button>
                      <div className="ml-auto flex items-center gap-1">
                        <div className="w-16">
                          <NumberInput
                            label="From"
                            value={s.start}
                            min={0}
                            max={MAX_VIDEO_SECONDS}
                            disabled={!editable}
                            onChange={(start) => updateSubtitle(i, { start }, `sub${i}:s`)}
                          />
                        </div>
                        <div className="w-16">
                          <NumberInput
                            label="To"
                            value={s.end}
                            min={0.1}
                            max={MAX_VIDEO_SECONDS}
                            disabled={!editable}
                            onChange={(end) => updateSubtitle(i, { end }, `sub${i}:e`)}
                          />
                        </div>
                        {editable && (
                          <Button
                            size="sm"
                            variant="ghost"
                            aria-label={`Remove caption ${i + 1}`}
                            onClick={() =>
                              set({ ...doc, subtitles: doc.subtitles.filter((_, k) => k !== i) })
                            }
                          >
                            ×
                          </Button>
                        )}
                      </div>
                    </div>
                    <Input
                      aria-label={`Caption ${i + 1} text`}
                      className="h-8"
                      maxLength={300}
                      value={s.text}
                      disabled={!editable}
                      onChange={(e) => updateSubtitle(i, { text: e.target.value }, `sub${i}:t`)}
                    />
                    {s.end <= s.start && (
                      <p className="text-xs text-danger">Must end after it starts.</p>
                    )}
                  </li>
                );
              })}
            </ol>
          </section>

          {/* Preview */}
          <section aria-label="Preview" className="flex min-w-0 flex-col items-center gap-3">
            <PreviewScreen
              doc={doc}
              orgId={organization.id}
              kinds={kinds}
              t={playback.t}
              playing={playback.playing}
            />
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                variant="ghost"
                aria-label="Back to start"
                onClick={() => playback.setT(0)}
              >
                ⏮
              </Button>
              <Button
                size="sm"
                variant="secondary"
                disabled={!doc.clips.length}
                onClick={() => {
                  if (playback.t >= total) playback.setT(0);
                  playback.setPlaying((p) => !p);
                }}
              >
                {playback.playing ? "Pause" : "Play"}
              </Button>
              <span className="font-mono text-xs text-muted">
                {round(playback.t).toFixed(1)}s / {round(total).toFixed(1)}s
              </span>
            </div>
            <p className="text-center text-xs text-muted">
              Approximate, muted preview. Render to see the exact result with audio.
            </p>
          </section>

          {/* Layout and audio */}
          <section aria-label="Layout" className="order-3 flex min-w-0 flex-col gap-3">
            <h3 className="text-sm font-semibold">Layout</h3>
            <fieldset disabled={!editable} className="flex flex-col gap-3">
              <label className="flex flex-col gap-1 text-xs font-medium">
                Aspect ratio
                <Select
                  className="h-8"
                  value={`${doc.width}x${doc.height}`}
                  onChange={(e) => {
                    const [w, h] = e.target.value.split("x").map(Number);
                    set({ ...doc, width: w, height: h });
                  }}
                >
                  {VIDEO_SIZES.map((s) => (
                    <option key={s.label} value={`${s.width}x${s.height}`}>
                      {s.label}
                    </option>
                  ))}
                </Select>
              </label>
              <label className="flex flex-col gap-1 text-xs font-medium">
                Frame rate
                <Select
                  className="h-8"
                  value={doc.fps}
                  onChange={(e) => set({ ...doc, fps: Number(e.target.value) as 24 | 25 | 30 })}
                >
                  <option value={24}>24 fps</option>
                  <option value={25}>25 fps</option>
                  <option value={30}>30 fps</option>
                </Select>
              </label>
              <div className="flex flex-col gap-1 text-xs font-medium">
                Cover image
                {doc.cover ? (
                  <div className="flex items-center gap-2">
                    {/* eslint-disable-next-line @next/next/no-img-element -- authenticated same-origin file */}
                    <img
                      src={assetUrl(organization.id, doc.cover)}
                      alt="Cover"
                      className="size-12 rounded object-cover"
                    />
                    <Button size="sm" variant="ghost" onClick={() => set({ ...doc, cover: null })}>
                      Remove
                    </Button>
                  </div>
                ) : (
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => setPicker({ mode: "cover" })}
                  >
                    Choose cover
                  </Button>
                )}
              </div>
            </fieldset>
            <div className="flex items-center justify-between gap-2 border-t border-border pt-3">
              <h3 className="text-sm font-semibold">Audio</h3>
              {editable && (
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={doc.audio.length >= 2}
                  onClick={() => setPicker({ mode: "audio" })}
                >
                  + Audio
                </Button>
              )}
            </div>
            {doc.audio.length === 0 && (
              <p className="text-xs text-muted">
                No music or voiceover. Original clip sound is muted.
              </p>
            )}
            <ul className="flex flex-col gap-2">
              {doc.audio.map((a, i) => (
                <li key={i} className="flex flex-col gap-2 rounded-md border border-border p-2">
                  <div className="flex items-center justify-between gap-2">
                    <span className="min-w-0 truncate text-sm">
                      {meta.get(a.asset.id)?.title || "Audio"}
                    </span>
                    {editable && (
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => set({ ...doc, audio: doc.audio.filter((_, k) => k !== i) })}
                      >
                        Remove
                      </Button>
                    )}
                  </div>
                  <div className="grid grid-cols-3 gap-2">
                    <label className="flex flex-col gap-1 text-xs font-medium">
                      Role
                      <Select
                        className="h-8 text-xs"
                        value={a.role}
                        disabled={!editable}
                        onChange={(e) =>
                          set({
                            ...doc,
                            audio: doc.audio.map((x, k) =>
                              k === i ? { ...x, role: e.target.value as "music" | "voiceover" } : x,
                            ),
                          })
                        }
                      >
                        <option value="music">Music</option>
                        <option value="voiceover">Voice</option>
                      </Select>
                    </label>
                    <NumberInput
                      label="Volume"
                      value={a.volume}
                      min={0}
                      max={2}
                      disabled={!editable}
                      onChange={(volume) =>
                        set(
                          {
                            ...doc,
                            audio: doc.audio.map((x, k) => (k === i ? { ...x, volume } : x)),
                          },
                          `aud${i}:v`,
                        )
                      }
                    />
                    <NumberInput
                      label="Starts"
                      value={a.start}
                      min={0}
                      max={MAX_VIDEO_SECONDS}
                      disabled={!editable}
                      onChange={(start) =>
                        set(
                          {
                            ...doc,
                            audio: doc.audio.map((x, k) => (k === i ? { ...x, start } : x)),
                          },
                          `aud${i}:s`,
                        )
                      }
                    />
                  </div>
                </li>
              ))}
            </ul>
            {caps.data && <p className="text-xs text-muted">{caps.data.ai_voiceover.note}</p>}
          </section>
        </div>

        {/* Timeline */}
        <section
          aria-label="Timeline"
          className="mt-4 flex flex-col gap-2 border-t border-border pt-3"
        >
          {editable && (
            <div className="flex flex-wrap items-center gap-2">
              <Button
                size="sm"
                onClick={() => setPicker({ mode: "clip" })}
                disabled={doc.clips.length >= 30}
              >
                + Add clip
              </Button>
              <Button
                size="sm"
                variant="secondary"
                onClick={splitAtPlayhead}
                disabled={!doc.clips.length}
              >
                Split at playhead
              </Button>
              {selectedClip && (
                <Button
                  size="sm"
                  variant="ghost"
                  className="text-danger"
                  onClick={() => removeClip(selectedClip.id)}
                >
                  Delete clip
                </Button>
              )}
              <span className="ml-auto text-xs text-muted">
                Click a clip to edit it; click the strip to move the playhead.
              </span>
            </div>
          )}
          <Timeline
            doc={doc}
            orgId={organization.id}
            meta={meta}
            t={playback.t}
            selectedId={selectedClipId}
            onSeek={(time) => {
              playback.setPlaying(false);
              playback.setT(time);
            }}
            onSelect={setSelectedClipId}
          />
        </section>

        {/* Selected clip */}
        {selectedClip && (
          <section aria-label="Selected clip" className="mt-4 rounded-md border border-border p-3">
            <fieldset disabled={!editable} className="flex flex-col gap-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h3 className="text-sm font-semibold">
                  Clip {selectedIndex + 1} · {info?.title || (isVideo ? "Video clip" : "Image")}
                  <span className="ml-2 font-normal text-muted">
                    starts at {round(starts[selectedIndex])}s
                  </span>
                </h3>
                {editable && (
                  <div className="flex flex-wrap gap-1">
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={selectedIndex === 0}
                      onClick={() => moveClip(selectedIndex, -1)}
                    >
                      ← Earlier
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={selectedIndex === doc.clips.length - 1}
                      onClick={() => moveClip(selectedIndex, 1)}
                    >
                      Later →
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => setPicker({ mode: "replace" })}
                    >
                      Replace media
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={doc.clips.length >= 30}
                      onClick={() => {
                        const copy = { ...selectedClip, id: uid("c") };
                        set({
                          ...doc,
                          clips: [
                            ...doc.clips.slice(0, selectedIndex + 1),
                            copy,
                            ...doc.clips.slice(selectedIndex + 1),
                          ],
                        });
                        setSelectedClipId(copy.id);
                      }}
                    >
                      Duplicate
                    </Button>
                  </div>
                )}
              </div>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                <NumberInput
                  label="Duration (s)"
                  value={selectedClip.duration}
                  min={0.5}
                  max={60}
                  onChange={(duration) =>
                    updateClip(selectedClip.id, { duration }, `${selectedClip.id}:d`)
                  }
                />
                {isVideo && (
                  <NumberInput
                    label="Start at (s)"
                    value={selectedClip.trim_start}
                    min={0}
                    max={maxTrim}
                    onChange={(trim_start) =>
                      updateClip(selectedClip.id, { trim_start }, `${selectedClip.id}:t`)
                    }
                  />
                )}
                {selectedIndex < doc.clips.length - 1 && (
                  <label className="flex flex-col gap-1 text-xs font-medium">
                    Transition to next
                    <Select
                      className="h-8"
                      value={selectedClip.transition}
                      onChange={(e) =>
                        updateClip(selectedClip.id, {
                          transition: e.target.value as Clip["transition"],
                        })
                      }
                    >
                      <option value="none">Cut</option>
                      <option value="fade">Fade</option>
                    </Select>
                  </label>
                )}
                {selectedClip.transition === "fade" && selectedIndex < doc.clips.length - 1 && (
                  <NumberInput
                    label="Fade (s)"
                    value={selectedClip.transition_duration}
                    min={0.2}
                    max={2}
                    onChange={(transition_duration) =>
                      updateClip(selectedClip.id, { transition_duration }, `${selectedClip.id}:f`)
                    }
                  />
                )}
              </div>
              {selectedClip.overlay ? (
                <div className="flex flex-col gap-2 rounded bg-neutral-soft p-2">
                  <div className="flex gap-2">
                    <Input
                      aria-label="Text overlay"
                      className="h-8"
                      value={selectedClip.overlay.text}
                      maxLength={200}
                      onChange={(e) =>
                        selectedClip.overlay &&
                        updateClip(
                          selectedClip.id,
                          { overlay: { ...selectedClip.overlay, text: e.target.value || " " } },
                          `${selectedClip.id}:o`,
                        )
                      }
                    />
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => updateClip(selectedClip.id, { overlay: null })}
                    >
                      Remove text
                    </Button>
                  </div>
                  <div className="flex flex-wrap items-end gap-3">
                    <label className="flex flex-col gap-1 text-xs font-medium">
                      Position
                      <Select
                        className="h-8 w-28"
                        value={selectedClip.overlay.position}
                        onChange={(e) =>
                          selectedClip.overlay &&
                          updateClip(selectedClip.id, {
                            overlay: {
                              ...selectedClip.overlay,
                              position: e.target.value as "top" | "center" | "bottom",
                            },
                          })
                        }
                      >
                        <option value="top">Top</option>
                        <option value="center">Center</option>
                        <option value="bottom">Bottom</option>
                      </Select>
                    </label>
                    <div className="w-24">
                      <NumberInput
                        label="Size"
                        step={1}
                        value={selectedClip.overlay.font_size}
                        min={12}
                        max={160}
                        onChange={(font_size) =>
                          selectedClip.overlay &&
                          updateClip(
                            selectedClip.id,
                            {
                              overlay: {
                                ...selectedClip.overlay,
                                font_size: Math.round(font_size),
                              },
                            },
                            `${selectedClip.id}:os`,
                          )
                        }
                      />
                    </div>
                    <label className="flex items-center gap-1 text-xs">
                      <input
                        type="checkbox"
                        checked={selectedClip.overlay.background}
                        onChange={(e) =>
                          selectedClip.overlay &&
                          updateClip(selectedClip.id, {
                            overlay: { ...selectedClip.overlay, background: e.target.checked },
                          })
                        }
                      />
                      Background
                    </label>
                    <ColorField
                      label="Color"
                      value={selectedClip.overlay.color}
                      onChange={(color) =>
                        selectedClip.overlay &&
                        updateClip(selectedClip.id, { overlay: { ...selectedClip.overlay, color } })
                      }
                      brandColors={palette.colors}
                    />
                  </div>
                </div>
              ) : (
                editable && (
                  <div>
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() =>
                        updateClip(selectedClip.id, {
                          overlay: {
                            text: "Your text",
                            position: "bottom",
                            color: "#ffffff",
                            font_size: Math.round(doc.width / 18),
                            background: true,
                          },
                        })
                      }
                    >
                      + Text overlay
                    </Button>
                  </div>
                )
              )}
            </fieldset>
          </section>
        )}
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <RenderPanel item={item} dirty={dirty} onSave={save} disabledReason={renderBlocked} />
        <StoryboardPanel
          item={item}
          editable={editable}
          onApplySubtitles={applySubtitles}
          onAddScene={(scene) => setPicker({ mode: "clip", scene })}
        />
      </div>

      {picker && (
        <AssetPickerDialog
          title={
            picker.mode === "audio"
              ? "Add audio"
              : picker.mode === "cover"
                ? "Choose a cover image"
                : picker.mode === "replace"
                  ? "Replace clip media"
                  : picker.scene
                    ? `Media for: ${picker.scene.description}`
                    : "Add a clip"
          }
          kinds={
            picker.mode === "audio"
              ? ["audio"]
              : picker.mode === "cover"
                ? ["image"]
                : ["image", "video"]
          }
          onPick={onPicked}
          onClose={() => setPicker(null)}
          generateSize={{ width: doc.width, height: doc.height }}
          includeBrand={picker.mode === "cover"}
        />
      )}
    </div>
  );
}
