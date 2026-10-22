"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { Alert } from "@/components/ui/alert";
import { PageLoading } from "@/components/ui/spinner";
import { useMe } from "@/hooks/use-me";
import { errorMessage } from "@/lib/api/errors";

const LAST_ORG_KEY = "amc:last-org";

export function rememberOrg(orgId: string) {
  try {
    localStorage.setItem(LAST_ORG_KEY, orgId);
  } catch {
    /* storage unavailable: harmless */
  }
}

/** Sends the visitor to sign-in, org creation, or their most recent organization. */
export function HomeRedirect() {
  const me = useMe();
  const router = useRouter();

  useEffect(() => {
    if (me.isPending || me.isError) return;
    if (!me.data) return router.replace("/login");
    const memberships = me.data.memberships;
    if (memberships.length === 0) return router.replace("/orgs/new");
    let last: string | null = null;
    try {
      last = localStorage.getItem(LAST_ORG_KEY);
    } catch {
      last = null;
    }
    const target = memberships.find((m) => m.organization.id === last) ?? memberships[0];
    router.replace(`/o/${target.organization.id}`);
  }, [me.data, me.isPending, me.isError, router]);

  if (me.isError) {
    return (
      <div className="mx-auto max-w-md p-8">
        <Alert tone="danger" title="We couldn't reach the server">
          {errorMessage(me.error)}
        </Alert>
      </div>
    );
  }
  return <PageLoading />;
}
