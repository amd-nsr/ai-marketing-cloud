"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { useOrg } from "@/hooks/use-org";
import { listNotifications, markNotificationsRead } from "@/lib/api/notifications";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

export function NotificationsBell() {
  const { organization } = useOrg();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const key = ["orgs", organization.id, "notifications"];
  const notes = useQuery({
    queryKey: key,
    queryFn: () => listNotifications(organization.id),
    refetchInterval: 60_000,
  });
  const unread = notes.data?.results.filter((n) => !n.read_at).length ?? 0;

  const toggle = async () => {
    const next = !open;
    setOpen(next);
    if (next && unread > 0) {
      await markNotificationsRead(organization.id).catch(() => null);
      void queryClient.invalidateQueries({ queryKey: key });
    }
  };

  return (
    <div className="relative">
      <button
        type="button"
        onClick={toggle}
        aria-expanded={open}
        aria-label={unread ? `Notifications, ${unread} unread` : "Notifications"}
        className="flex w-full items-center justify-between rounded-md px-2 py-1.5 text-sm text-muted hover:bg-neutral-soft hover:text-foreground"
      >
        Notifications
        {unread > 0 && (
          <span className="rounded-full bg-danger px-1.5 text-xs font-medium text-white">
            {unread}
          </span>
        )}
      </button>
      {open && (
        <div className="absolute bottom-full left-0 z-50 mb-2 w-72 rounded-lg border border-border bg-surface p-2 shadow-lg">
          {notes.data?.results.length === 0 && (
            <p className="p-2 text-sm text-muted">You&apos;re all caught up.</p>
          )}
          <ul className="flex max-h-80 flex-col overflow-y-auto">
            {notes.data?.results.map((n) => (
              <li key={n.id}>
                <Link
                  href={n.link || "#"}
                  onClick={() => setOpen(false)}
                  className={cn(
                    "block rounded p-2 hover:bg-neutral-soft",
                    !n.read_at && "bg-info-soft/40",
                  )}
                >
                  <p className="text-sm font-medium">{n.title}</p>
                  {n.body && <p className="line-clamp-2 text-xs text-muted">{n.body}</p>}
                  <p className="text-xs text-muted">{formatDateTime(n.created_at)}</p>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
