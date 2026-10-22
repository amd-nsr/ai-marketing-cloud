import { Suspense } from "react";

import { AuthShell } from "@/components/layout/auth-shell";
import { ResetPasswordForm } from "@/features/auth/reset-password-form";

export const metadata = { title: "Choose a new password" };

export default function ResetPasswordPage() {
  return (
    <AuthShell title="Choose a new password">
      <Suspense>
        <ResetPasswordForm />
      </Suspense>
    </AuthShell>
  );
}
