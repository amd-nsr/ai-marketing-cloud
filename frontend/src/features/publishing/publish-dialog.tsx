"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input, Select } from "@/components/ui/input";
import { useToast } from "@/components/ui/toast";
import { useOrg } from "@/hooks/use-org";
import type { ContentItem } from "@/lib/api/content";
import { errorMessage } from "@/lib/api/errors";
import { requestPublish } from "@/lib/api/publishing";
import { listSocialAccounts } from "@/lib/api/social";
import { PLATFORM_LABEL } from "@/features/content/labels";

function composeText(item: ContentItem): string {
  const v = item.current_version;
  if (!v) return "";
  const parts = [v.caption.trim()];
  if (v.cta && !v.caption.includes(v.cta.trim())) parts.push(v.cta.trim());
  if (v.hashtags.length) parts.push(v.hashtags.join(" "));
  return parts.filter(Boolean).join("\n\n");
}

/** Shows exactly what will be posted, where, and when, before anything is sent. */
export function PublishDialog({ item, onClose }: { item: ContentItem; onClose: () => void }) {
  const { organization } = useOrg();
  const queryClient = useQueryClient();
  const toast = useToast();
  const accounts = useQuery({
    queryKey: ["orgs", organization.id, "social-accounts", item.platform],
    queryFn: () => listSocialAccounts(organization.id, item.platform),
  });
  const usable = (accounts.data?.results ?? []).filter((a) => a.is_usable);
  const [accountId, setAccountId] = useState("");
  const [when, setWhen] = useState<"now" | "later">("now");
  const [at, setAt] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  // One key per dialog: double-clicks and retries of this request can't create two posts.
  const [idempotencyKey] = useState(() => crypto.randomUUID());

  const account = usable.find((a) => a.id === (accountId || usable[0]?.id));
  const scheduledFor = when === "later" && at ? new Date(at) : null;

  const submit = async () => {
    setError(null);
    if (!account) return setError("Choose an account.");
    if (when === "later" && (!scheduledFor || scheduledFor.getTime() < Date.now() + 60_000)) {
      return setError("Pick a time at least a minute from now.");
    }
    setPending(true);
    try {
      const job = await requestPublish(
        organization.id,
        {
          content_item: item.id,
          social_account: account.id,
          scheduled_for: scheduledFor?.toISOString() ?? null,
        },
        idempotencyKey,
      );
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["orgs", organization.id, "content"] }),
        queryClient.invalidateQueries({ queryKey: ["orgs", organization.id, "publishing"] }),
      ]);
      toast(job.status === "scheduled" ? "Post scheduled." : "Publishing now…");
      onClose();
    } catch (e) {
      setError(errorMessage(e));
      setPending(false);
    }
  };

  return (
    <Dialog
      open
      onClose={() => !pending && onClose()}
      title={`Publish to ${PLATFORM_LABEL[item.platform]}`}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={pending}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={pending || !account}>
            {pending ? "Sending…" : when === "now" ? "Publish now" : "Schedule"}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        {accounts.data && usable.length === 0 && (
          <Alert tone="warning" title={`No connected ${PLATFORM_LABEL[item.platform]} account`}>
            <Link href={`/o/${organization.id}/accounts`} className="underline">
              Connect an account
            </Link>{" "}
            first.
          </Alert>
        )}
        {usable.length > 0 && (
          <>
            <Field label="Account">
              {(p) => (
                <Select
                  value={account?.id ?? ""}
                  onChange={(e) => setAccountId(e.target.value)}
                  {...p}
                >
                  {usable.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name}
                      {a.is_mock ? " (simulation)" : ""}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
            <fieldset className="flex flex-col gap-2">
              <legend className="mb-1 text-sm font-medium">When</legend>
              <label className="flex items-center gap-2 text-sm">
                <input type="radio" checked={when === "now"} onChange={() => setWhen("now")} /> Now
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input type="radio" checked={when === "later"} onChange={() => setWhen("later")} />{" "}
                At a specific time
              </label>
              {when === "later" && (
                <Input
                  type="datetime-local"
                  aria-label="Publish at"
                  value={at}
                  onChange={(e) => setAt(e.target.value)}
                />
              )}
            </fieldset>
            <div className="rounded-md border border-border p-3">
              <p className="mb-2 flex flex-wrap items-center gap-2 text-xs text-muted">
                What will be posted to{" "}
                <span className="font-medium text-foreground">{account?.name}</span>
                {account?.is_mock && (
                  <Badge tone="warning">Simulation: nothing is posted for real</Badge>
                )}
              </p>
              <p className="max-h-48 overflow-y-auto text-sm whitespace-pre-line">
                {composeText(item)}
              </p>
              {item.asset_count > 0 && (
                <p className="mt-2 text-xs text-muted">
                  + {item.asset_count} image{item.asset_count > 1 ? "s" : ""}
                </p>
              )}
            </div>
          </>
        )}
        {error && <Alert tone="danger">{error}</Alert>}
      </div>
    </Dialog>
  );
}
