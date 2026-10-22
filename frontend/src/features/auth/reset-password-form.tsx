"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { confirmPasswordReset } from "@/lib/api/auth";
import { applyServerErrors } from "@/lib/validation/forms";
import { zodResolver } from "@/lib/validation/zod-resolver";

const schema = z
  .object({
    new_password: z.string().min(12, "Use at least 12 characters."),
    confirm: z.string(),
  })
  .refine((v) => v.new_password === v.confirm, {
    path: ["confirm"],
    message: "Passwords don't match.",
  });
type Values = z.infer<typeof schema>;

export function ResetPasswordForm() {
  const params = useSearchParams();
  const uid = params.get("uid");
  const token = params.get("token");
  const [done, setDone] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<Values>({ resolver: zodResolver(schema) });

  if (!uid || !token) {
    return <Alert tone="danger">This reset link is incomplete. Request a new one.</Alert>;
  }
  if (done) {
    return (
      <Alert tone="success" title="Password updated">
        <Link href="/login" className="underline">
          Sign in with your new password
        </Link>
      </Alert>
    );
  }

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null);
    try {
      await confirmPasswordReset({ uid, token, new_password: values.new_password });
      setDone(true);
    } catch (error) {
      const message = applyServerErrors(error, setError, ["new_password"]);
      setFormError(message);
    }
  });

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
      {formError && <Alert tone="danger">{formError}</Alert>}
      <Field label="New password" error={errors.new_password?.message}>
        {(p) => (
          <Input type="password" autoComplete="new-password" {...p} {...register("new_password")} />
        )}
      </Field>
      <Field label="Confirm password" error={errors.confirm?.message}>
        {(p) => (
          <Input type="password" autoComplete="new-password" {...p} {...register("confirm")} />
        )}
      </Field>
      <Button type="submit" disabled={isSubmitting}>
        {isSubmitting ? "Saving…" : "Set new password"}
      </Button>
    </form>
  );
}
