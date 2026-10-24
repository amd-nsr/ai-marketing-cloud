"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { type ChangeEvent, useEffect, useRef, useState } from "react";

import { MockAIBadge } from "@/components/features/ai-badges";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmDialog, Dialog } from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input, Select, Textarea } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { Tabs } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/toast";
import { useBrandAssets } from "@/features/brand/queries";
import { useOrg } from "@/hooks/use-org";
import { useWorkflowRun } from "@/hooks/use-workflow-run";
import {
  deleteLibraryAsset,
  generateLibraryImage,
  type LibraryAsset,
  uploadLibraryAsset,
} from "@/lib/api/content";
import { errorMessage } from "@/lib/api/errors";
import { cn } from "@/lib/utils";

import type { AssetRef } from "./document";
import { studioKeys, useLibrary, useStudioCapabilities } from "./queries";

export type AssetKind = "image" | "video" | "audio";

export interface PickedAsset {
  ref: AssetRef;
  url: string;
  kind: AssetKind;
  width: number | null;
  height: number | null;
  duration: number | null;
  title: string;
}

const ACCEPT: Record<AssetKind, string[]> = {
  image: ["image/png", "image/jpeg", "image/webp"],
  video: ["video/mp4", "video/quicktime", "video/webm"],
  audio: ["audio/mpeg", "audio/mp4", "audio/x-m4a", "audio/wav", "audio/x-wav", "audio/ogg"],
};

function formatBytes(n: number) {
  return n > 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(1)} MB` : `${Math.ceil(n / 1024)} KB`;
}

export function toPicked(a: LibraryAsset): PickedAsset {
  return {
    ref: { source: "library", id: a.id },
    url: a.file_url,
    kind: a.kind,
    width: a.width,
    height: a.height,
    duration: a.duration_seconds,
    title: a.title || a.original_filename,
  };
}

function Thumb({ asset }: { asset: LibraryAsset }) {
  if (asset.kind === "image")
    return (
      // eslint-disable-next-line @next/next/no-img-element -- authenticated same-origin file
      <img
        src={asset.file_url}
        alt={asset.title}
        loading="lazy"
        className="aspect-square w-full bg-neutral-soft object-cover"
      />
    );
  if (asset.kind === "video")
    return (
      <video
        src={asset.file_url}
        muted
        preload="metadata"
        className="aspect-square w-full bg-black object-cover"
      />
    );
  return (
    <div className="flex aspect-square w-full items-center justify-center bg-neutral-soft text-3xl">
      <span aria-hidden>♪</span>
    </div>
  );
}

function GenerateImageDialog({
  onClose,
  onCreated,
  size,
}: {
  onClose: () => void;
  onCreated: (asset: { id: string }) => void;
  size?: { width: number; height: number };
}) {
  const { organization } = useOrg();
  const queryClient = useQueryClient();
  const caps = useStudioCapabilities();
  const [prompt, setPrompt] = useState("");
  const [style, setStyle] = useState("");
  const [aspect, setAspect] = useState(
    size && size.height > size.width * 1.4
      ? "story"
      : size && size.height > size.width
        ? "portrait"
        : "square",
  );
  const [runId, setRunId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const run = useWorkflowRun(organization.id, runId);
  const dims = { square: [1024, 1024], portrait: [1024, 1280], story: [1024, 1792] }[aspect] ?? [
    1024, 1024,
  ];

  useEffect(() => {
    if (run.data?.status === "succeeded") {
      void queryClient.invalidateQueries({ queryKey: studioKeys.library(organization.id) });
      onCreated({ id: String(run.data.output.asset_id) });
    }
  }, [run.data, queryClient, organization.id, onCreated]);

  const start = async () => {
    setError(null);
    if (prompt.trim().length < 5) return setError("Describe the image you want.");
    try {
      const created = await generateLibraryImage(organization.id, {
        prompt: prompt.trim(),
        visual_style: style.trim(),
        width: dims[0],
        height: dims[1],
      });
      setRunId(created.id);
    } catch (e) {
      setError(errorMessage(e));
    }
  };
  const working = runId !== null && run.data?.status !== "failed";
  const failed = run.data?.status === "failed";

  return (
    <Dialog
      open
      onClose={onClose}
      title="Generate an image"
      description="The image is added to your media library, where you can reuse it."
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={start} disabled={working || !caps.data?.image_generation.available}>
            {working ? "Generating…" : failed ? "Try again" : "Generate"}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        {caps.data?.image_generation.is_mock && (
          <Alert tone="warning">
            Development mode: this creates a labelled placeholder, not a real AI image.
          </Alert>
        )}
        {error && <Alert tone="danger">{error}</Alert>}
        {failed && <Alert tone="danger">{run.data?.error_message}</Alert>}
        <Field label="What should the image show?">
          {(p) => (
            <Textarea
              rows={3}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="A latte with heart-shaped foam on a wooden counter, morning light"
              {...p}
            />
          )}
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Style" optional>
            {(p) => (
              <Input
                value={style}
                onChange={(e) => setStyle(e.target.value)}
                placeholder="Natural photo, warm tones"
                {...p}
              />
            )}
          </Field>
          <Field label="Shape">
            {(p) => (
              <Select value={aspect} onChange={(e) => setAspect(e.target.value)} {...p}>
                <option value="square">Square</option>
                <option value="portrait">Portrait 4:5</option>
                <option value="story">Tall 9:16</option>
              </Select>
            )}
          </Field>
        </div>
        {working && (
          <p className="flex items-center gap-2 text-sm text-muted">
            <Spinner /> Generating your image…
          </p>
        )}
      </div>
    </Dialog>
  );
}

/**
 * Browse, search, upload, and (when available) generate organization media.
 * With ``onPick`` it acts as a picker; otherwise it manages the library.
 */
export function LibraryBrowser({
  kinds = ["image", "video", "audio"],
  onPick,
  generateSize,
  includeBrand = true,
}: {
  kinds?: AssetKind[];
  onPick?: (asset: PickedAsset) => void;
  generateSize?: { width: number; height: number };
  includeBrand?: boolean;
}) {
  const { organization, can } = useOrg();
  const queryClient = useQueryClient();
  const toast = useToast();
  const caps = useStudioCapabilities();
  const [source, setSource] = useState<"library" | "brand">("library");
  const [kind, setKind] = useState<string>(kinds.length === 1 ? kinds[0] : "");
  const [q, setQ] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [deleting, setDeleting] = useState<LibraryAsset | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const library = useLibrary({ kind: kind || kinds.join(","), q: q.trim() });
  const brand = useBrandAssets();
  const canEdit = can("content.edit");
  const showBrand = includeBrand && kinds.includes("image");
  const accept = kinds.flatMap((k) => ACCEPT[k]);
  const maxMedia = caps.data?.max_media_upload_bytes ?? 100 * 1024 * 1024;
  const maxImage = caps.data?.max_image_upload_bytes ?? 10 * 1024 * 1024;

  const refresh = () =>
    queryClient.invalidateQueries({ queryKey: studioKeys.library(organization.id) });
  const upload = useMutation({
    mutationFn: (file: File) => uploadLibraryAsset(organization.id, file),
    onSuccess: async (asset) => {
      await refresh();
      toast(`${asset.title || "File"} added to the library.`);
    },
    onError: (e) => setError(errorMessage(e)),
  });
  const remove = useMutation({
    mutationFn: (id: string) => deleteLibraryAsset(organization.id, id),
    onSuccess: async () => {
      setDeleting(null);
      await refresh();
    },
    onError: (e) => {
      setDeleting(null);
      toast(errorMessage(e), "danger");
    },
  });

  const onFile = (e: ChangeEvent<HTMLInputElement>) => {
    setError(null);
    const files = Array.from(e.target.files ?? []);
    e.target.value = "";
    for (const file of files) {
      const isImage = file.type.startsWith("image/");
      if (!accept.includes(file.type)) {
        setError(`${file.name}: this file type isn't supported here.`);
        continue;
      }
      const limit = isImage ? maxImage : maxMedia;
      if (file.size > limit) {
        setError(`${file.name} is larger than ${formatBytes(limit)}.`);
        continue;
      }
      upload.mutate(file);
    }
  };

  return (
    <div className="flex flex-col gap-3">
      {showBrand && (
        <Tabs
          label="Asset source"
          value={source}
          onChange={setSource}
          items={[
            { value: "library", label: "Media library", count: library.data?.count },
            { value: "brand", label: "Brand kit", count: brand.data?.count },
          ]}
        />
      )}
      {source === "library" && (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <Input
              aria-label="Search media"
              placeholder="Search by name"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              className="w-full sm:w-56"
            />
            {kinds.length > 1 && (
              <Select
                aria-label="Media type"
                value={kind}
                onChange={(e) => setKind(e.target.value)}
                className="w-36"
              >
                <option value="">All types</option>
                {kinds.map((k) => (
                  <option key={k} value={k}>
                    {k === "image" ? "Images" : k === "video" ? "Videos" : "Audio"}
                  </option>
                ))}
              </Select>
            )}
            {canEdit && (
              <div className="ml-auto flex gap-2">
                <input
                  ref={input}
                  type="file"
                  multiple
                  accept={accept.join(",")}
                  className="hidden"
                  onChange={onFile}
                  aria-label="Choose files to upload"
                />
                {kinds.includes("image") && caps.data?.image_generation.available && (
                  <Button size="sm" variant="secondary" onClick={() => setGenerating(true)}>
                    Generate image
                  </Button>
                )}
                <Button
                  size="sm"
                  onClick={() => input.current?.click()}
                  disabled={upload.isPending}
                >
                  {upload.isPending ? "Uploading…" : "Upload"}
                </Button>
              </div>
            )}
          </div>
          {kinds.includes("image") && caps.data && !caps.data.image_generation.available && (
            <p className="text-xs text-muted">{caps.data.image_generation.note}</p>
          )}
          {error && <Alert tone="danger">{error}</Alert>}
          {library.isPending && <Spinner />}
          {library.isError && <Alert tone="danger">{errorMessage(library.error)}</Alert>}
          {library.data?.count === 0 && (
            <p className="rounded-lg border border-dashed border-border p-6 text-center text-sm text-muted">
              No media yet. Upload photos, logos, clips, or music to reuse them in any design.
            </p>
          )}
          <ul className="grid grid-cols-3 gap-2 sm:grid-cols-4 lg:grid-cols-5">
            {library.data?.results.map((a) => (
              <li
                key={a.id}
                className="group relative overflow-hidden rounded-md border border-border"
              >
                <button
                  type="button"
                  disabled={!onPick}
                  onClick={() => onPick?.(toPicked(a))}
                  className={cn("block w-full text-left", onPick && "hover:opacity-90")}
                  title={a.title}
                >
                  <Thumb asset={a} />
                  <span className="block truncate px-1.5 py-1 text-xs">
                    {a.title || "Untitled"}
                  </span>
                </button>
                <div className="pointer-events-none absolute top-1 left-1 flex flex-wrap gap-1">
                  {a.kind !== "image" && (
                    <Badge>
                      {a.kind === "video" ? "Video" : "Audio"}
                      {a.duration_seconds ? ` · ${a.duration_seconds.toFixed(1)}s` : ""}
                    </Badge>
                  )}
                  {a.source === "ai_generated" &&
                    (a.is_mock ? <MockAIBadge isMock /> : <Badge tone="info">AI</Badge>)}
                </div>
                {canEdit && !onPick && (
                  <button
                    type="button"
                    onClick={() => setDeleting(a)}
                    className="absolute top-1 right-1 rounded bg-black/60 px-1.5 text-xs text-white opacity-0 group-hover:opacity-100 focus:opacity-100"
                    aria-label={`Delete ${a.title}`}
                  >
                    ×
                  </button>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
      {source === "brand" && (
        <>
          {brand.data?.count === 0 && (
            <p className="text-sm text-muted">
              No brand assets yet. Add logos and approved images under Brand.
            </p>
          )}
          <ul className="grid grid-cols-3 gap-2 sm:grid-cols-4 lg:grid-cols-5">
            {brand.data?.results
              .filter((b) => b.content_type.startsWith("image/"))
              .map((b) => (
                <li key={b.id} className="overflow-hidden rounded-md border border-border">
                  <button
                    type="button"
                    disabled={!onPick}
                    onClick={() =>
                      onPick?.({
                        ref: { source: "brand", id: b.id },
                        url: b.file_url,
                        kind: "image",
                        width: b.width,
                        height: b.height,
                        duration: null,
                        title: b.title || b.original_filename,
                      })
                    }
                    className="block w-full text-left"
                  >
                    {/* eslint-disable-next-line @next/next/no-img-element -- authenticated same-origin file */}
                    <img
                      src={b.file_url}
                      alt={b.title || "Brand asset"}
                      className="aspect-square w-full bg-neutral-soft object-contain"
                    />
                    <span className="block truncate px-1.5 py-1 text-xs">
                      {b.kind === "logo" ? "Logo · " : ""}
                      {b.title || b.original_filename}
                    </span>
                  </button>
                </li>
              ))}
          </ul>
        </>
      )}
      {generating && (
        <GenerateImageDialog
          size={generateSize}
          onClose={() => setGenerating(false)}
          onCreated={() => {
            setGenerating(false);
            toast("Image added to your library.");
          }}
        />
      )}
      <ConfirmDialog
        open={deleting !== null}
        onCancel={() => setDeleting(null)}
        onConfirm={() => deleting && remove.mutate(deleting.id)}
        title="Delete this file?"
        description="It's removed from the library. Files used by a current design can't be deleted."
        confirmLabel="Delete"
        pending={remove.isPending}
      />
    </div>
  );
}

/** A modal picker around ``LibraryBrowser``. */
export function AssetPickerDialog({
  title = "Choose media",
  kinds,
  onPick,
  onClose,
  generateSize,
  includeBrand = true,
}: {
  title?: string;
  kinds: AssetKind[];
  onPick: (asset: PickedAsset) => void;
  onClose: () => void;
  generateSize?: { width: number; height: number };
  includeBrand?: boolean;
}) {
  return (
    <Dialog open onClose={onClose} title={title}>
      <div className="max-h-[60vh] overflow-y-auto">
        <LibraryBrowser
          kinds={kinds}
          onPick={onPick}
          generateSize={generateSize}
          includeBrand={includeBrand}
        />
      </div>
    </Dialog>
  );
}
