import Link from "next/link";
import { Suspense } from "react";

import { AuthShell } from "@/components/layout/auth-shell";
import { RegisterForm } from "@/features/auth/register-form";

export const metadata = { title: "Create account" };

export default function RegisterPage() {
  return (
    <AuthShell
      title="Create your account"
      description="Start planning and publishing your marketing in one place."
      footer={
        <>
          Already have an account?{" "}
          <Link href="/login" className="text-primary hover:underline">
            Sign in
          </Link>
        </>
      }
    >
      <Suspense>
        <RegisterForm />
      </Suspense>
    </AuthShell>
  );
}
