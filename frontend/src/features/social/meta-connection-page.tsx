"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button, buttonClasses } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { PageLoading } from "@/components/ui/spinner";
import { useToast } from "@/components/ui/toast";
import { useOrg } from "@/hooks/use-org";
import { errorMessage } from "@/lib/api/errors";
import {
  connectAdAccounts,
  connectPages,
  getMetaConnection,
  type MetaConnection,
  refreshMetaConnection,
} from "@/lib/api/meta";
import { formatDate, formatDateTime } from "@/lib/format";

const STATUS: Record<
  MetaConnection["status"],
  { label: string; tone: "success" | "danger" | "neutral" }
> = {
  active: { label: "Connected", tone: "success" },
  needs_reauth: { label: "Reconnect required", tone: "danger" },
  revoked: { label: "Access removed on Facebook", tone: "danger" },
  disconnected: { label: "Disconnected", tone: "neutral" },
  deleted: { label: "Data deleted", tone: "neutral" },
};

function Selectable({
  label,
  hint,
  checked,
  disabled,
  connected,
  onToggle,
}: {
  label: string;
  hint: string;
  checked: boolean;
  disabled: boolean;
  connected: boolean;
  onToggle: () => void;
}) {
  return (
    <label
      className={
        disabled
          ? "flex items-start gap-3 rounded-lg border border-border p-3 opacity-60"
          : "flex cursor-pointer items-start gap-3 rounded-lg border border-border p-3 hover:bg-neutral-soft"
      }
    >
      <input
        type="checkbox"
        className="mt-1"
        checked={checked || connected}
        disabled={disabled || connected}
        onChange={onToggle}
      />
      <span className="flex min-w-0 flex-col">
        <span className="flex flex-wrap items-center gap-2 font-medium">
          {label}
          {connected && <Badge tone="success">Connected</Badge>}
        </span>
        <span className="text-xs text-muted">{hint}</span>
      </span>
    </label>
  );
}

export function MetaConnectionPage() {
  const { connectionId } = useParams<{ connectionId: string }>();
  const { organization, can } = useOrg();
  const queryClient = useQueryClient();
  const toast = useToast();
  const key = ["orgs", organization.id, "meta-connections", connectionId];
  const connection = useQuery({
    queryKey: key,
    queryFn: () => getMetaConnection(organization.id, connectionId),
  });
  const [pages, setPages] = useState<string[]>([]);
  const [adAccounts, setAdAccounts] = useState<string[]>([]);

  const invalidate = () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: ["orgs", organization.id, "meta-connections"] }),
      queryClient.invalidateQueries({ queryKey: ["orgs", organization.id, "social-accounts"] }),
      queryClient.invalidateQueries({ queryKey: ["orgs", organization.id, "ads"] }),
    ]);
  const refresh = useMutation({
    mutationFn: () => refreshMetaConnection(organization.id, connectionId),
    onSuccess: async () => {
      toast("Refreshed from Meta.");
      await invalidate();
    },
    onError: (e) => toast(errorMessage(e), "danger"),
  });
  const savePages = useMutation({
    mutationFn: () => connectPages(organization.id, connectionId, pages),
    onSuccess: async () => {
      toast(`${pages.length} Page${pages.length === 1 ? "" : "s"} connected.`);
      setPages([]);
      await invalidate();
    },
    onError: (e) => toast(errorMessage(e), "danger"),
  });
  const saveAdAccounts = useMutation({
    mutationFn: () => connectAdAccounts(organization.id, connectionId, adAccounts),
    onSuccess: async () => {
      toast(`${adAccounts.length} ad account${adAccounts.length === 1 ? "" : "s"} connected.`);
      setAdAccounts([]);
      await invalidate();
    },
    onError: (e) => toast(errorMessage(e), "danger"),
  });

  if (connection.isPending) return <PageLoading />;
  if (connection.isError) return <Alert tone="danger">{errorMessage(connection.error)}</Alert>;
  const c = connection.data;
  const manage = can("social.manage");
  const manageAds = can("ads.manage");
  const pagesFeature = c.features.find((f) => f.feature === "pages");
  const adsFeature = c.features.find((f) => f.feature === "ads_read");
  const toggle = (list: string[], set: (v: string[]) => void, id: string) =>
    set(list.includes(id) ? list.filter((x) => x !== id) : [...list, id]);

  return (
    <>
      <PageHeader
        title={c.is_mock ? "Simulated Meta login" : `Meta login: ${c.name || "Facebook"}`}
        description="Choose which Facebook Pages and ad accounts this organization may use. Nothing is connected until you select it."
        actions={
          <Link href={`/o/${organization.id}/accounts`} className={buttonClasses("secondary")}>
            Back to accounts
          </Link>
        }
      />
      <div className="flex flex-col gap-6">
        {c.is_mock && (
          <Alert tone="warning" title="Simulation">
            These Pages and ad accounts are simulated: nothing is posted to Facebook and no money is
            spent.
          </Alert>
        )}
        <Card>
          <CardHeader
            title="Connection"
            actions={
              manage &&
              c.is_usable && (
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => refresh.mutate()}
                  disabled={refresh.isPending}
                >
                  {refresh.isPending ? "Refreshing…" : "Refresh from Meta"}
                </Button>
              )
            }
          />
          <div className="flex flex-col gap-3 text-sm">
            <p className="flex flex-wrap items-center gap-2">
              <Badge tone={STATUS[c.status].tone}>{STATUS[c.status].label}</Badge>
              {c.is_mock && <Badge tone="warning">Simulation</Badge>}
              {c.token_expires_at && (
                <span className="text-muted">
                  Login valid until {formatDate(c.token_expires_at)}
                </span>
              )}
            </p>
            {c.last_error && <p className="text-danger">{c.last_error}</p>}
            <ul className="flex flex-col gap-1.5">
              {c.features.map((f) => (
                <li key={f.feature} className="flex flex-wrap items-center gap-2">
                  <span aria-hidden>{f.available ? "✓" : "✗"}</span>
                  <span>{f.label}</span>
                  {!f.available && (
                    <span className="text-xs text-muted">Missing: {f.missing.join(", ")}</span>
                  )}
                </li>
              ))}
            </ul>
            {c.declined_permissions.length > 0 && (
              <p className="text-xs text-muted">
                You declined some permissions. Connect again from Social accounts and allow them to
                use those features.
              </p>
            )}
            {c.assets_refreshed_at && (
              <p className="text-xs text-muted">
                Assets checked {formatDateTime(c.assets_refreshed_at)}.
              </p>
            )}
          </div>
        </Card>

        <Card>
          <CardHeader
            title="Facebook Pages"
            description="Approved content is published to the Pages you connect."
          />
          {c.pages.length === 0 ? (
            <p className="text-sm text-muted">No Pages were shared with this app.</p>
          ) : (
            <div className="flex flex-col gap-2">
              {c.pages.map((p) => (
                <Selectable
                  key={p.id}
                  label={p.name}
                  hint={
                    p.can_publish
                      ? p.category || "Facebook Page"
                      : "You can't publish to this Page (no content access)."
                  }
                  checked={pages.includes(p.id)}
                  connected={p.connected}
                  disabled={!manage || !p.can_publish || !pagesFeature?.available || !c.is_usable}
                  onToggle={() => toggle(pages, setPages, p.id)}
                />
              ))}
              {manage && (
                <div>
                  <Button
                    onClick={() => savePages.mutate()}
                    disabled={pages.length === 0 || savePages.isPending}
                  >
                    {savePages.isPending ? "Connecting…" : "Connect selected Pages"}
                  </Button>
                </div>
              )}
            </div>
          )}
        </Card>

        {c.ads_enabled && (
          <Card>
            <CardHeader
              title="Ad accounts"
              description="Campaigns, spend and results sync from the ad accounts you connect. Changes run only under your advertising limits."
            />
            {!adsFeature?.available ? (
              <p className="text-sm text-muted">
                Ads permissions weren&apos;t granted. Connect again and allow them to use ads.
              </p>
            ) : c.ad_accounts.length === 0 ? (
              <p className="text-sm text-muted">No ad accounts were found for this login.</p>
            ) : (
              <div className="flex flex-col gap-2">
                {c.ad_accounts.map((a) => (
                  <Selectable
                    key={a.id}
                    label={`${a.name} (${a.currency})`}
                    hint={a.is_active ? a.id : `${a.id} · not active on Meta`}
                    checked={adAccounts.includes(a.id)}
                    connected={a.connected}
                    disabled={!manageAds || !c.is_usable}
                    onToggle={() => toggle(adAccounts, setAdAccounts, a.id)}
                  />
                ))}
                {manageAds && (
                  <div>
                    <Button
                      onClick={() => saveAdAccounts.mutate()}
                      disabled={adAccounts.length === 0 || saveAdAccounts.isPending}
                    >
                      {saveAdAccounts.isPending ? "Connecting…" : "Connect selected ad accounts"}
                    </Button>
                  </div>
                )}
              </div>
            )}
          </Card>
        )}
      </div>
    </>
  );
}
