import { Suspense } from "react";

import { AuthShell } from "@/components/layout/auth-shell";
import { AcceptInvitation } from "@/features/auth/accept-invitation";

export const metadata = { title: "Accept invitation" };

export default function AcceptInvitationPage() {
  return (
    <AuthShell title="Join your team" description="You've been invited to an organization.">
      <Suspense>
        <AcceptInvitation />
      </Suspense>
    </AuthShell>
  );
}
