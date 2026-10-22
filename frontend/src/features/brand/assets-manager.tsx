"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { type ChangeEvent, useRef, useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { Select } from "@/components/ui/input";
import { PageLoading } from "@/components/ui/spinner";
import { useToast } from "@/components/ui/toast";
import { useOrg } from "@/hooks/use-org";
import { type BrandAsset, deleteBrandAsset, uploadBrandAsset } from "@/lib/api/brand";
import { errorMessage } from "@/lib/api/errors";

import { brandDependents, brandKeys, useBrandAssets } from "./queries";

const MAX_BYTES = 10 * 1024 * 1024;
const ACCEPT = "image/png,image/jpeg,image/webp";
const KIND_LABEL: Record<BrandAsset["kind"], string> = {
  logo: "Logo",
  image: "Approved image",
  other: "Other",
};

function formatBytes(n: number) {
  if (n < 1024) return `${n} B`;
  return n < 1024 * 1024 ? `${Math.round(n / 1024)} KB` : `${(n / 1024 / 1024).toFixed(1)} MB`;
}

export function AssetsManager() {
  const { organization, can } = useOrg();
  const queryClient = useQueryClient();
  const toast = useToast();
  const assets = useBrandAssets();
  const inputRef = useRef<HTMLInputElement>(null);
  const [kind, setKind] = useState<BrandAsset["kind"]>("logo");
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<BrandAsset | null>(null);
  const canEdit = can("brand.edit");

  const invalidate = () =>
    Promise.all(
      [brandKeys.assets(organization.id), ...brandDependents(organization.id)].map((k) =>
        queryClient.invalidateQueries({ queryKey: k }),
      ),
    );

  const upload = useMutation({
    mutationFn: (file: File) => uploadBrandAsset(organization.id, file, kind),
    onSuccess: () => {
      toast("Asset uploaded.");
      return invalidate();
    },
    onError: (e) => setError(errorMessage(e)),
  });
  const remove = useMutation({
    mutationFn: (id: string) => deleteBrandAsset(organization.id, id),
    onSuccess: () => {
      setDeleting(null);
      toast("Asset deleted.");
      return invalidate();
    },
    onError: (e) => toast(errorMessage(e), "danger"),
  });

  const onFile = (e: ChangeEvent<HTMLInputElement>) => {
    setError(null);
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    if (!ACCEPT.split(",").includes(file.type))
      return setError("Choose a PNG, JPEG, or WebP image.");
    if (file.size > MAX_BYTES) return setError("Images must be 10 MB or smaller.");
    upload.mutate(file);
  };

  return (
    <div className="flex flex-col gap-4">
      {canEdit && (
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex flex-col gap-1.5">
            <label htmlFor="asset-kind" className="text-sm font-medium">
              Type
            </label>
            <Select
              id="asset-kind"
              value={kind}
              onChange={(e) => setKind(e.target.value as BrandAsset["kind"])}
              className="w-44"
            >
              {Object.entries(KIND_LABEL).map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </Select>
          </div>
          <input
            ref={inputRef}
            type="file"
            accept={ACCEPT}
            className="hidden"
            onChange={onFile}
            aria-label="Choose image"
          />
          <Button onClick={() => inputRef.current?.click()} disabled={upload.isPending}>
            {upload.isPending ? "Uploading…" : "Upload image"}
          </Button>
          <p className="text-xs text-muted">PNG, JPEG, or WebP up to 10 MB.</p>
        </div>
      )}
      {error && <Alert tone="danger">{error}</Alert>}
      {assets.isPending && <PageLoading />}
      {assets.data && assets.data.results.length === 0 && (
        <EmptyState
          title="No brand assets yet"
          description="Upload your logo and approved images so content can stay on-brand."
        />
      )}
      {assets.data && assets.data.results.length > 0 && (
        <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {assets.data.results.map((a) => (
            <li key={a.id} className="overflow-hidden rounded-lg border border-border">
              <div className="flex aspect-square items-center justify-center bg-neutral-soft p-2">
                {/* eslint-disable-next-line @next/next/no-img-element -- authenticated same-origin file, not optimizable */}
                <img
                  src={a.file_url}
                  alt={a.title || a.original_filename || KIND_LABEL[a.kind]}
                  className="max-h-full max-w-full object-contain"
                />
              </div>
              <div className="flex flex-col gap-1 p-3">
                <div className="flex items-center justify-between gap-2">
                  <Badge>{KIND_LABEL[a.kind]}</Badge>
                  {canEdit && (
                    <Button variant="ghost" size="sm" onClick={() => setDeleting(a)}>
                      Delete
                    </Button>
                  )}
                </div>
                <p className="truncate text-xs text-muted" title={a.original_filename}>
                  {a.width}×{a.height} · {formatBytes(a.size_bytes)}
                </p>
              </div>
            </li>
          ))}
        </ul>
      )}
      <ConfirmDialog
        open={deleting !== null}
        onCancel={() => setDeleting(null)}
        onConfirm={() => deleting && remove.mutate(deleting.id)}
        pending={remove.isPending}
        title="Delete asset?"
        description="The file is permanently deleted from storage."
        confirmLabel="Delete"
      />
    </div>
  );
}
