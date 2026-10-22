"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/dialog";
import { PageHeader } from "@/components/ui/page-header";
import { PageLoading } from "@/components/ui/spinner";
import { useToast } from "@/components/ui/toast";
import { useOrg } from "@/hooks/use-org";
import { errorMessage } from "@/lib/api/errors";
import {
  disconnectAccount,
  listPlatforms,
  listSocialAccounts,
  type PlatformInfo,
  type SocialAccount,
  startConnection,
} from "@/lib/api/social";
import { formatDate } from "@/lib/format";
import { FORMAT_LABEL } from "@/features/content/labels";

const STATUS = {
  connected: { label: "Connected", tone: "success" },
  needs_reauth: { label: "Reconnect required", tone: "danger" },
  disconnected: { label: "Disconnected", tone: "neutral" },
} as const;

function PlatformCard({
  info,
  accounts,
  onDisconnect,
}: {
  info: PlatformInfo;
  accounts: SocialAccount[];
  onDisconnect: (a: SocialAccount) => void;
}) {
  const { organization, can } = useOrg();
  const toast = useToast();
  const [pending, setPending] = useState<"real" | "sim" | null>(null);
  const manage = can("social.manage");

  const connect = async (simulation: boolean) => {
    setPending(simulation ? "sim" : "real");
    try {
      const { authorization_url } = await startConnection(
        organization.id,
        info.platform,
        simulation,
      );
      window.location.assign(authorization_url);
    } catch (e) {
      toast(errorMessage(e), "danger");
      setPending(null);
    }
  };

  return (
    <Card>
      <CardHeader
        title={info.display_name}
        description={`Publishes: ${info.publish_formats.map((f) => FORMAT_LABEL[f as keyof typeof FORMAT_LABEL] ?? f).join(", ")}`}
        actions={
          info.configured ? (
            <Badge tone="success">Available</Badge>
          ) : (
            <Badge tone="warning">Not configured</Badge>
          )
        }
      />
      {accounts.length > 0 && (
        <ul className="mb-4 flex flex-col divide-y divide-border rounded-md border border-border">
          {accounts.map((a) => (
            <li key={a.id} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2">
              <div className="min-w-0">
                <p className="truncate text-sm font-medium">
                  {a.name} {a.username && <span className="text-muted">@{a.username}</span>}
                </p>
                <p className="text-xs text-muted">
                  Connected {formatDate(a.connected_at)}
                  {a.connected_by_email && ` by ${a.connected_by_email}`}
                </p>
                {a.status === "needs_reauth" && a.last_error && (
                  <p className="text-xs text-danger">{a.last_error}</p>
                )}
              </div>
              <div className="flex items-center gap-2">
                {a.is_mock && <Badge tone="warning">Simulation</Badge>}
                <Badge tone={STATUS[a.status].tone}>{STATUS[a.status].label}</Badge>
                {manage && (
                  <Button size="sm" variant="ghost" onClick={() => onDisconnect(a)}>
                    Disconnect
                  </Button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
      <ul className="mb-4 list-disc pl-5 text-xs text-muted">
        {info.notes.map((n) => (
          <li key={n}>{n}</li>
        ))}
      </ul>
      {manage && (
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => connect(false)} disabled={!info.configured || pending !== null}>
            {pending === "real"
              ? "Redirecting…"
              : accounts.some((a) => !a.is_mock)
                ? "Connect another"
                : "Connect"}
          </Button>
          {info.simulation_available && (
            <Button variant="secondary" onClick={() => connect(true)} disabled={pending !== null}>
              {pending === "sim" ? "Connecting…" : "Add simulation account"}
            </Button>
          )}
        </div>
      )}
      {!info.configured && manage && (
        <p className="mt-2 text-xs text-muted">
          An administrator must register an app with {info.display_name.split(" ")[0]} and add its
          credentials to the server configuration before real accounts can be connected.
        </p>
      )}
    </Card>
  );
}

export function AccountsPage() {
  const { organization } = useOrg();
  const queryClient = useQueryClient();
  const toast = useToast();
  const [disconnecting, setDisconnecting] = useState<SocialAccount | null>(null);
  const platforms = useQuery({
    queryKey: ["orgs", organization.id, "platforms"],
    queryFn: () => listPlatforms(organization.id),
  });
  const accounts = useQuery({
    queryKey: ["orgs", organization.id, "social-accounts"],
    queryFn: () => listSocialAccounts(organization.id),
  });
  const disconnect = useMutation({
    mutationFn: (id: string) => disconnectAccount(organization.id, id),
    onSuccess: () => {
      setDisconnecting(null);
      toast("Account disconnected.");
      return queryClient.invalidateQueries({
        queryKey: ["orgs", organization.id, "social-accounts"],
      });
    },
    onError: (e) => toast(errorMessage(e), "danger"),
  });

  const anySimulation = accounts.data?.results.some((a) => a.is_mock);

  return (
    <>
      <PageHeader
        title="Social accounts"
        description="Where your approved content gets published. Access tokens are encrypted and never shown in the browser."
      />
      {anySimulation && (
        <Alert tone="warning" className="mb-4" title="Simulation accounts">
          Simulation accounts behave like real ones but never post anything to a real platform. Use
          them to try the full workflow.
        </Alert>
      )}
      {(platforms.isPending || accounts.isPending) && <PageLoading />}
      {platforms.isError && <Alert tone="danger">{errorMessage(platforms.error)}</Alert>}
      {platforms.data && accounts.data && (
        <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
          {platforms.data.map((p) => (
            <PlatformCard
              key={p.platform}
              info={p}
              accounts={accounts.data.results.filter((a) => a.platform === p.platform)}
              onDisconnect={setDisconnecting}
            />
          ))}
        </div>
      )}
      <ConfirmDialog
        open={disconnecting !== null}
        onCancel={() => setDisconnecting(null)}
        onConfirm={() => disconnecting && disconnect.mutate(disconnecting.id)}
        pending={disconnect.isPending}
        title={`Disconnect ${disconnecting?.name}?`}
        description="Its stored credentials are deleted and any scheduled posts to it are cancelled. Published posts stay on the platform."
        confirmLabel="Disconnect"
      />
    </>
  );
}
