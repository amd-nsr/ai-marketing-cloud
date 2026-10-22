"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { ME_QUERY_KEY } from "@/hooks/use-me";
import { register as registerUser } from "@/lib/api/auth";
import { safeNextPath } from "@/lib/auth/redirect";
import { applyServerErrors } from "@/lib/validation/forms";
import { zodResolver } from "@/lib/validation/zod-resolver";

const schema = z.object({
  full_name: z.string().trim().max(150),
  email: z.string().trim().email("Enter a valid email address."),
  password: z.string().min(12, "Use at least 12 characters."),
});
type Values = z.infer<typeof schema>;

export function RegisterForm() {
  const router = useRouter();
  const params = useSearchParams();
  const queryClient = useQueryClient();
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { full_name: "" } });

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null);
    try {
      const me = await registerUser(values);
      queryClient.setQueryData(ME_QUERY_KEY, me);
      router.replace(safeNextPath(params.get("next"), "/orgs/new"));
    } catch (error) {
      setFormError(applyServerErrors(error, setError, ["email", "password", "full_name"]));
    }
  });

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
      {formError && <Alert tone="danger">{formError}</Alert>}
      <Field label="Full name" optional error={errors.full_name?.message}>
        {(p) => <Input autoComplete="name" {...p} {...register("full_name")} />}
      </Field>
      <Field label="Work email" error={errors.email?.message}>
        {(p) => <Input type="email" autoComplete="email" {...p} {...register("email")} />}
      </Field>
      <Field label="Password" error={errors.password?.message} hint="At least 12 characters.">
        {(p) => (
          <Input type="password" autoComplete="new-password" {...p} {...register("password")} />
        )}
      </Field>
      <Button type="submit" disabled={isSubmitting}>
        {isSubmitting ? "Creating account…" : "Create account"}
      </Button>
    </form>
  );
}
