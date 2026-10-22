"use client";

import Link from "next/link";
import { useParams, usePathname, useRouter } from "next/navigation";
import { type ReactNode, useEffect } from "react";

import { AppShell } from "@/components/layout/app-shell";
import { Alert } from "@/components/ui/alert";
import { buttonClasses } from "@/components/ui/button";
import { PageLoading } from "@/components/ui/spinner";
import { useMe } from "@/hooks/use-me";
import { OrgProvider } from "@/hooks/use-org";
import { errorMessage } from "@/lib/api/errors";

/** Resolves the signed-in user and their membership for the org in the URL. */
export function OrgGate({ children }: { children: ReactNode }) {
  const { orgId } = useParams<{ orgId: string }>();
  const me = useMe();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (me.data === null) router.replace(`/login?next=${encodeURIComponent(pathname)}`);
  }, [me.data, pathname, router]);

  if (me.isPending || me.data === null) return <PageLoading />;
  if (me.isError) {
    return (
      <div className="mx-auto max-w-md p-8">
        <Alert tone="danger" title="Couldn't load your account">
          {errorMessage(me.error)}
        </Alert>
      </div>
    );
  }

  const membership = me.data.memberships.find((m) => m.organization.id === orgId);
  if (!membership) {
    return (
      <div className="mx-auto flex max-w-md flex-col gap-4 p-8">
        <Alert tone="warning" title="Organization not found">
          It doesn&apos;t exist or you&apos;re not a member.
        </Alert>
        <Link href="/" className={buttonClasses("secondary")}>
          Go to my organizations
        </Link>
      </div>
    );
  }

  return (
    <OrgProvider membership={membership}>
      <AppShell me={me.data}>{children}</AppShell>
    </OrgProvider>
  );
}
