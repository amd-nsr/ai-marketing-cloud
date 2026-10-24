"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button, buttonClasses } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/dialog";
import { useToast } from "@/components/ui/toast";
import { useOrg } from "@/hooks/use-org";
import { errorMessage } from "@/lib/api/errors";
import { disconnectMeta, listMetaConnections, type MetaConnection } from "@/lib/api/meta";

/** Meta logins (Facebook Login grants) and what was selected through each. */
export function MetaLogins() {
  const { organization, can } = useOrg();
  const queryClient = useQueryClient();
  const toast = useToast();
  const [disconnecting, setDisconnecting] = useState<MetaConnection | null>(null);
  const connections = useQuery({
    queryKey: ["orgs", organization.id, "meta-connections"],
    queryFn: () => listMetaConnections(organization.id),
  });
  const disconnect = useMutation({
    mutationFn: (id: string) => disconnectMeta(organization.id, id),
    onSuccess: async () => {
      setDisconnecting(null);
      toast("Meta login disconnected and access removed on Facebook.");
      await Promise.all(
        ["meta-connections", "social-accounts", "ads"].map((k) =>
          queryClient.invalidateQueries({ queryKey: ["orgs", organization.id, k] }),
        ),
      );
    },
    onError: (e) => toast(errorMessage(e), "danger"),
  });
  const items = connections.data?.results ?? [];
  if (items.length === 0) return null;
  return (
    <Card className="mb-4">
      <CardHeader
        title="Meta logins"
        description="Facebook Pages and ad accounts are chosen from a Meta login. Disconnecting a login disconnects everything chosen through it."
      />
      <ul className="flex flex-col divide-y divide-border">
        {items.map((c) => {
          const pages = c.pages.filter((p) => p.connected).length;
          const ads = c.ad_accounts.filter((a) => a.connected).length;
          return (
            <li key={c.id} className="flex flex-wrap items-center gap-3 py-3 first:pt-0 last:pb-0">
              <div className="flex min-w-0 flex-1 flex-col gap-1">
                <span className="flex flex-wrap items-center gap-2 font-medium">
                  {c.is_mock ? "Simulated Meta login" : c.name || "Meta login"}
                  {c.is_mock && <Badge tone="warning">Simulation</Badge>}
                  {c.status !== "active" && <Badge tone="danger">Reconnect required</Badge>}
                </span>
                <span className="text-xs text-muted">
                  {pages} Page{pages === 1 ? "" : "s"}
                  {c.ads_enabled && ` · ${ads} ad account${ads === 1 ? "" : "s"}`} connected
                  {c.features.some((f) => !f.available) && " · some permissions missing"}
                </span>
              </div>
              <Link
                href={`/o/${organization.id}/accounts/meta/${c.id}`}
                className={buttonClasses("secondary", "sm")}
              >
                Choose Pages and ad accounts
              </Link>
              {can("social.manage") && (
                <Button variant="ghost" size="sm" onClick={() => setDisconnecting(c)}>
                  Disconnect
                </Button>
              )}
            </li>
          );
        })}
      </ul>
      <ConfirmDialog
        open={disconnecting !== null}
        onCancel={() => setDisconnecting(null)}
        onConfirm={() => disconnecting && disconnect.mutate(disconnecting.id)}
        pending={disconnect.isPending}
        title="Disconnect this Meta login?"
        description="This app's access is removed on Facebook, its Pages and ad accounts are disconnected here, and scheduled posts and pending ad changes are cancelled. Running ad campaigns are not paused on Meta: pause them first if you need to."
        confirmLabel="Disconnect"
      />
    </Card>
  );
}
