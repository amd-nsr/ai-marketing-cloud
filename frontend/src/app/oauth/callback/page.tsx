import { Suspense } from "react";

import { AuthShell } from "@/components/layout/auth-shell";
import { OAuthCallback } from "@/features/social/oauth-callback";

export const metadata = { title: "Connecting account" };

export default function Page() {
  return (
    <AuthShell title="Connecting your account">
      <Suspense>
        <OAuthCallback />
      </Suspense>
    </AuthShell>
  );
}
