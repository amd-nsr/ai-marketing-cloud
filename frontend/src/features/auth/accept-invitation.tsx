"use client";

import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button, buttonClasses } from "@/components/ui/button";
import { PageLoading } from "@/components/ui/spinner";
import { ME_QUERY_KEY, useMe } from "@/hooks/use-me";
import { errorMessage } from "@/lib/api/errors";
import { acceptInvitation } from "@/lib/api/organizations";

export function AcceptInvitation() {
  const params = useSearchParams();
  const token = params.get("token");
  const router = useRouter();
  const queryClient = useQueryClient();
  const me = useMe();
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  if (!token) return <Alert tone="danger">This invitation link is incomplete.</Alert>;
  if (me.isPending) return <PageLoading />;

  const here = `/invitations/accept?token=${encodeURIComponent(token)}`;
  if (!me.data) {
    return (
      <div className="flex flex-col gap-3">
        <p className="text-sm text-muted">
          Sign in or create an account with the invited email address.
        </p>
        <Link href={`/login?next=${encodeURIComponent(here)}`} className={buttonClasses()}>
          Sign in
        </Link>
        <Link
          href={`/register?next=${encodeURIComponent(here)}`}
          className={buttonClasses("secondary")}
        >
          Create account
        </Link>
      </div>
    );
  }

  const accept = async () => {
    setPending(true);
    setError(null);
    try {
      const membership = await acceptInvitation(token);
      await queryClient.invalidateQueries({ queryKey: ME_QUERY_KEY });
      router.replace(`/o/${membership.organization.id}`);
    } catch (e) {
      setError(errorMessage(e));
      setPending(false);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      {error && <Alert tone="danger">{error}</Alert>}
      <p className="text-sm">
        Signed in as <span className="font-medium">{me.data.user.email}</span>.
      </p>
      <Button onClick={accept} disabled={pending}>
        {pending ? "Joining…" : "Accept invitation"}
      </Button>
    </div>
  );
}
