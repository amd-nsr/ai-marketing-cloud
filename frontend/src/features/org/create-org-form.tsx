"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { ME_QUERY_KEY } from "@/hooks/use-me";
import { createOrganization } from "@/lib/api/organizations";
import { applyServerErrors } from "@/lib/validation/forms";
import { zodResolver } from "@/lib/validation/zod-resolver";

const schema = z.object({
  name: z.string().trim().min(2, "Enter at least 2 characters.").max(120),
});
type Values = z.infer<typeof schema>;

export function CreateOrgForm() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<Values>({ resolver: zodResolver(schema) });

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null);
    try {
      const org = await createOrganization(values);
      await queryClient.invalidateQueries({ queryKey: ME_QUERY_KEY });
      router.replace(`/o/${org.id}`);
    } catch (error) {
      setFormError(applyServerErrors(error, setError, ["name"]));
    }
  });

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
      {formError && <Alert tone="danger">{formError}</Alert>}
      <Field label="Business or organization name" error={errors.name?.message}>
        {(p) => <Input autoComplete="organization" {...p} {...register("name")} />}
      </Field>
      <Button type="submit" disabled={isSubmitting}>
        {isSubmitting ? "Creating…" : "Create organization"}
      </Button>
    </form>
  );
}
