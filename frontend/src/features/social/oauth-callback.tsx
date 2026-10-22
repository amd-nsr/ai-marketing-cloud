"use client";

import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { Alert } from "@/components/ui/alert";
import { buttonClasses } from "@/components/ui/button";
import { PageLoading } from "@/components/ui/spinner";
import { errorMessage } from "@/lib/api/errors";
import { completeConnection } from "@/lib/api/social";

/** Platforms redirect here after the user grants (or denies) access. */
export function OAuthCallback() {
  const params = useSearchParams();
  const router = useRouter();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const started = useRef(false);
  const state = params.get("state");
  const code = params.get("code");
  const denied = params.get("error") ?? params.get("error_reason");

  useEffect(() => {
    if (started.current || !state || !code || denied) return;
    started.current = true; // the state is single-use; never submit twice
    completeConnection(state, code)
      .then(async (result) => {
        await queryClient.invalidateQueries({
          queryKey: ["orgs", result.organization_id, "social-accounts"],
        });
        router.replace(`/o/${result.organization_id}/accounts?connected=${result.accounts.length}`);
      })
      .catch((e: unknown) => setError(errorMessage(e)));
  }, [state, code, denied, queryClient, router]);

  if (denied) {
    return (
      <Alert tone="warning" title="Connection cancelled">
        Access wasn&apos;t granted, so nothing was connected.
      </Alert>
    );
  }
  if (!state || !code)
    return <Alert tone="danger">This link is incomplete. Start the connection again.</Alert>;
  if (error) {
    return (
      <div className="flex flex-col gap-3">
        <Alert tone="danger" title="Couldn't connect the account">
          {error}
        </Alert>
        <Link href="/" className={buttonClasses("secondary")}>
          Back to the app
        </Link>
      </div>
    );
  }
  return <PageLoading label="Connecting your account…" />;
}
