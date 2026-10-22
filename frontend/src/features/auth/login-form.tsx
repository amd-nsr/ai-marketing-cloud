"use client";

import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { ME_QUERY_KEY } from "@/hooks/use-me";
import { login } from "@/lib/api/auth";
import { errorMessage } from "@/lib/api/errors";
import { safeNextPath } from "@/lib/auth/redirect";
import { zodResolver } from "@/lib/validation/zod-resolver";

const schema = z.object({
  email: z.string().trim().email("Enter a valid email address."),
  password: z.string().min(1, "Enter your password."),
});
type Values = z.infer<typeof schema>;

export function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const queryClient = useQueryClient();
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<Values>({ resolver: zodResolver(schema) });

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null);
    try {
      const me = await login(values);
      queryClient.setQueryData(ME_QUERY_KEY, me);
      router.replace(safeNextPath(params.get("next")));
    } catch (error) {
      setFormError(errorMessage(error));
    }
  });

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
      {formError && <Alert tone="danger">{formError}</Alert>}
      <Field label="Email" error={errors.email?.message}>
        {(p) => <Input type="email" autoComplete="email" {...p} {...register("email")} />}
      </Field>
      <Field label="Password" error={errors.password?.message}>
        {(p) => (
          <Input type="password" autoComplete="current-password" {...p} {...register("password")} />
        )}
      </Field>
      <div className="-mt-2 text-right text-sm">
        <Link href="/forgot-password" className="text-primary hover:underline">
          Forgot password?
        </Link>
      </div>
      <Button type="submit" disabled={isSubmitting}>
        {isSubmitting ? "Signing in…" : "Sign in"}
      </Button>
    </form>
  );
}
