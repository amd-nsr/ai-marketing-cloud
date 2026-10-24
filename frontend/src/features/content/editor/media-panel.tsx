"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { type ChangeEvent, useRef, useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { useToast } from "@/components/ui/toast";
import { useOrg } from "@/hooks/use-org";
import { type ContentItem, deleteAsset, uploadAsset } from "@/lib/api/content";
import { errorMessage } from "@/lib/api/errors";

import { contentKeys, useAssets, useRefreshItem } from "./queries";

const ACCEPT = ["image/png", "image/jpeg", "image/webp"];
const EDITABLE = new Set(["draft", "in_review", "changes_requested", "approved"]);

export function MediaPanel({ item }: { item: ContentItem }) {
  const { organization, can } = useOrg();
  const queryClient = useQueryClient();
  const toast = useToast();
  const refresh = useRefreshItem();
  const assets = useAssets(item.id);
  const input = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);
  const editable = can("content.edit") && EDITABLE.has(item.status);

  const after = async () => {
    await queryClient.invalidateQueries({ queryKey: contentKeys.assets(organization.id, item.id) });
    await refresh();
  };
  const upload = useMutation({
    mutationFn: (file: File) => uploadAsset(organization.id, item.id, file),
    onSuccess: after,
    onError: (e) => setError(errorMessage(e)),
  });
  const remove = useMutation({
    mutationFn: (assetId: string) => deleteAsset(organization.id, item.id, assetId),
    onSuccess: after,
    onError: (e) => toast(errorMessage(e), "danger"),
  });

  const onFile = (e: ChangeEvent<HTMLInputElement>) => {
    setError(null);
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    if (!ACCEPT.includes(file.type)) return setError("Choose a PNG, JPEG, or WebP image.");
    if (file.size > 10 * 1024 * 1024) return setError("Images must be 10 MB or smaller.");
    upload.mutate(file);
  };

  return (
    <Card>
      <CardHeader
        title="Media"
        description={
          item.document_kind
            ? "Exports of the design or video appear here automatically. You can also attach your own images."
            : "Images attached to this post."
        }
        actions={
          editable && (
            <>
              <input
                ref={input}
                type="file"
                accept={ACCEPT.join(",")}
                className="hidden"
                onChange={onFile}
                aria-label="Choose image"
              />
              <Button
                size="sm"
                variant="secondary"
                onClick={() => input.current?.click()}
                disabled={upload.isPending}
              >
                {upload.isPending ? "Uploading…" : "Add image"}
              </Button>
            </>
          )
        }
      />
      {error && <Alert tone="danger">{error}</Alert>}
      {assets.data && assets.data.length === 0 && (
        <p className="text-sm text-muted">No media yet.</p>
      )}
      {assets.data && assets.data.length > 0 && (
        <ul className="grid grid-cols-3 gap-2">
          {assets.data.map((a) => (
            <li key={a.id} className="group relative overflow-hidden rounded border border-border">
              {a.content_type.startsWith("video/") ? (
                <video
                  src={a.file_url}
                  muted
                  preload="metadata"
                  className="aspect-square w-full bg-black object-cover"
                />
              ) : (
                // eslint-disable-next-line @next/next/no-img-element -- authenticated same-origin file
                <img
                  src={a.file_url}
                  alt={item.current_version?.alt_text || "Attached image"}
                  className="aspect-square w-full object-cover"
                />
              )}
              <span className="absolute bottom-1 left-1 rounded bg-black/60 px-1 text-[10px] text-white">
                {a.source === "render" ? `Export · v${a.version_number ?? "?"}` : "Upload"}
              </span>
              {editable && (
                <button
                  type="button"
                  onClick={() => remove.mutate(a.id)}
                  className="absolute top-1 right-1 rounded bg-black/60 px-1.5 text-xs text-white opacity-0 group-hover:opacity-100 focus:opacity-100"
                  aria-label="Remove image"
                >
                  ×
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
