"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { requestPasswordReset } from "@/lib/api/auth";
import { errorMessage } from "@/lib/api/errors";
import { zodResolver } from "@/lib/validation/zod-resolver";

const schema = z.object({ email: z.string().trim().email("Enter a valid email address.") });
type Values = z.infer<typeof schema>;

export function ForgotPasswordForm() {
  const [sent, setSent] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<Values>({ resolver: zodResolver(schema) });

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null);
    try {
      const result = await requestPasswordReset(values);
      setSent(result.detail);
    } catch (error) {
      setFormError(errorMessage(error));
    }
  });

  if (sent) return <Alert tone="success">{sent}</Alert>;

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
      {formError && <Alert tone="danger">{formError}</Alert>}
      <Field label="Email" error={errors.email?.message}>
        {(p) => <Input type="email" autoComplete="email" {...p} {...register("email")} />}
      </Field>
      <Button type="submit" disabled={isSubmitting}>
        {isSubmitting ? "Sending…" : "Send reset link"}
      </Button>
    </form>
  );
}
