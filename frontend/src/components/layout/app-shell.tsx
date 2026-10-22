"use client";

import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { type ReactNode, useState } from "react";

import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/input";
import { ME_QUERY_KEY } from "@/hooks/use-me";
import { useOrg } from "@/hooks/use-org";
import { logout, type Me } from "@/lib/api/auth";
import { ROLE_LABELS } from "@/lib/auth/roles";
import { cn } from "@/lib/utils";

import { NAV_ITEMS, NAV_SECTIONS } from "./nav";
import { ModeBadge } from "./mode-badge";
import { NotificationsBell } from "./notifications-bell";

function OrgSwitcher({ me }: { me: Me }) {
  const { organization } = useOrg();
  const router = useRouter();
  const pathname = usePathname();
  const prefix = `/o/${organization.id}`;
  const subpath = pathname.startsWith(prefix) ? pathname.slice(prefix.length) : "";
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor="org-switcher" className="text-xs font-medium text-muted">
        Organization
      </label>
      <Select
        id="org-switcher"
        value={organization.id}
        onChange={(e) => {
          if (e.target.value === "__new__") router.push("/orgs/new");
          // Keep the same section when switching, but drop object-specific segments.
          else router.push(`/o/${e.target.value}${subpath.split("/").slice(0, 2).join("/")}`);
        }}
      >
        {me.memberships.map((m) => (
          <option key={m.organization.id} value={m.organization.id}>
            {m.organization.name}
          </option>
        ))}
        <option value="__new__">+ New organization</option>
      </Select>
    </div>
  );
}

/** The visible nav item whose path is the longest prefix of the current path. */
function activeHref(pathname: string, base: string, hrefs: string[]): string | null {
  let best: string | null = null;
  for (const href of hrefs) {
    const full = `${base}${href}`;
    const matches =
      href === "" ? pathname === base : pathname === full || pathname.startsWith(`${full}/`);
    if (matches && (best === null || href.length > best.length)) best = href;
  }
  return best;
}

function Nav({ onNavigate }: { onNavigate?: () => void }) {
  const { organization, can } = useOrg();
  const pathname = usePathname();
  const base = `/o/${organization.id}`;
  const visible = NAV_ITEMS.filter((i) => !i.permission || can(i.permission));
  const current = activeHref(
    pathname,
    base,
    visible.map((i) => i.href),
  );
  return (
    <nav aria-label="Main" className="flex flex-col gap-5">
      {NAV_SECTIONS.map((section) => {
        const items = visible.filter((i) => i.section === section);
        if (items.length === 0) return null;
        return (
          <div key={section}>
            <p className="mb-1 px-2 text-xs font-medium tracking-wide text-muted uppercase">
              {section}
            </p>
            <ul className="flex flex-col gap-0.5">
              {items.map((item) => {
                const active = item.href === current;
                return (
                  <li key={item.href}>
                    <Link
                      href={`${base}${item.href}`}
                      onClick={onNavigate}
                      aria-current={active ? "page" : undefined}
                      className={cn(
                        "block rounded-md px-2 py-1.5 text-sm",
                        active
                          ? "bg-neutral-soft font-medium"
                          : "text-muted hover:bg-neutral-soft hover:text-foreground",
                      )}
                    >
                      {item.label}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        );
      })}
    </nav>
  );
}

function UserMenu({ me }: { me: Me }) {
  const { membership } = useOrg();
  const router = useRouter();
  const queryClient = useQueryClient();
  const signOut = async () => {
    await logout().catch(() => null);
    queryClient.clear();
    queryClient.setQueryData(ME_QUERY_KEY, null);
    router.replace("/login");
  };
  return (
    <div className="flex flex-col gap-2 border-t border-border pt-4">
      <div className="min-w-0 px-2">
        <p className="truncate text-sm font-medium">{me.user.full_name || me.user.email}</p>
        <p className="truncate text-xs text-muted">
          {me.user.email} · {ROLE_LABELS[membership.role]}
        </p>
      </div>
      <div className="flex gap-2 px-2">
        <Link href="/account" className="text-xs text-muted hover:text-foreground">
          Account
        </Link>
        <button
          type="button"
          onClick={signOut}
          className="text-xs text-muted hover:text-foreground"
        >
          Sign out
        </button>
      </div>
    </div>
  );
}

export function AppShell({ me, children }: { me: Me; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const { organization } = useOrg();
  const sidebar = (
    <div className="flex h-full flex-col gap-6 p-4">
      <Link href={`/o/${organization.id}`} className="px-2 text-sm font-semibold text-primary">
        AI Marketing Cloud
      </Link>
      <OrgSwitcher me={me} />
      <ModeBadge />
      <div className="flex-1 overflow-y-auto">
        <Nav onNavigate={() => setOpen(false)} />
      </div>
      <NotificationsBell />
      <UserMenu me={me} />
    </div>
  );

  return (
    <div className="flex min-h-screen flex-1">
      <aside className="sticky top-0 hidden h-screen w-64 shrink-0 border-r border-border bg-surface lg:block">
        {sidebar}
      </aside>

      {open && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <button
            type="button"
            aria-label="Close menu"
            className="absolute inset-0 bg-black/40"
            onClick={() => setOpen(false)}
          />
          <aside className="absolute inset-y-0 left-0 w-72 max-w-[85vw] bg-surface shadow-xl">
            {sidebar}
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex items-center gap-3 border-b border-border bg-surface px-4 py-3 lg:hidden">
          <Button variant="ghost" size="sm" aria-label="Open menu" onClick={() => setOpen(true)}>
            ☰
          </Button>
          <span className="truncate text-sm font-medium">{organization.name}</span>
        </header>
        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
          {children}
        </main>
      </div>
    </div>
  );
}
