"use client";

import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { PageHeader } from "@/components/ui/page-header";
import { PageLoading } from "@/components/ui/spinner";
import { useToast } from "@/components/ui/toast";
import { ME_QUERY_KEY, useMe } from "@/hooks/use-me";
import { changePassword, updateProfile } from "@/lib/api/auth";
import { applyServerErrors } from "@/lib/validation/forms";
import { zodResolver } from "@/lib/validation/zod-resolver";

const profileSchema = z.object({ full_name: z.string().trim().max(150) });
const passwordSchema = z
  .object({
    current_password: z.string().min(1, "Enter your current password."),
    new_password: z.string().min(12, "Use at least 12 characters."),
    confirm: z.string(),
  })
  .refine((v) => v.new_password === v.confirm, {
    path: ["confirm"],
    message: "Passwords don't match.",
  });

export function Account() {
  const me = useMe();
  const router = useRouter();
  const toast = useToast();
  const queryClient = useQueryClient();
  const profile = useForm<z.infer<typeof profileSchema>>({
    resolver: zodResolver(profileSchema),
    values: { full_name: me.data?.user.full_name ?? "" },
  });
  const password = useForm<z.infer<typeof passwordSchema>>({
    resolver: zodResolver(passwordSchema),
  });

  useEffect(() => {
    if (me.data === null) router.replace("/login?next=/account");
  }, [me.data, router]);
  if (!me.data) return <PageLoading />;

  const saveProfile = profile.handleSubmit(async (values) => {
    try {
      const updated = await updateProfile(values);
      queryClient.setQueryData(ME_QUERY_KEY, updated);
      toast("Profile saved.");
    } catch (error) {
      const message = applyServerErrors(error, profile.setError, ["full_name"]);
      if (message) toast(message, "danger");
    }
  });

  const savePassword = password.handleSubmit(async (values) => {
    try {
      await changePassword({
        current_password: values.current_password,
        new_password: values.new_password,
      });
      password.reset();
      toast("Password changed.");
    } catch (error) {
      const message = applyServerErrors(error, password.setError, [
        "current_password",
        "new_password",
      ]);
      if (message) toast(message, "danger");
    }
  });

  return (
    <main className="mx-auto w-full max-w-2xl px-4 py-8">
      <Link href="/" className="text-sm text-primary hover:underline">
        ← Back to workspace
      </Link>
      <div className="mt-4">
        <PageHeader title="Your account" description={me.data.user.email} />
      </div>
      <div className="flex flex-col gap-6">
        <Card>
          <CardHeader title="Profile" />
          <form
            onSubmit={saveProfile}
            noValidate
            className="flex flex-col gap-4 sm:flex-row sm:items-end"
          >
            <Field
              label="Full name"
              className="flex-1"
              error={profile.formState.errors.full_name?.message}
            >
              {(p) => <Input {...p} {...profile.register("full_name")} />}
            </Field>
            <Button type="submit" disabled={profile.formState.isSubmitting}>
              Save
            </Button>
          </form>
        </Card>
        <Card>
          <CardHeader title="Change password" />
          <form onSubmit={savePassword} noValidate className="flex flex-col gap-4">
            <Field
              label="Current password"
              error={password.formState.errors.current_password?.message}
            >
              {(p) => (
                <Input
                  type="password"
                  autoComplete="current-password"
                  {...p}
                  {...password.register("current_password")}
                />
              )}
            </Field>
            <Field label="New password" error={password.formState.errors.new_password?.message}>
              {(p) => (
                <Input
                  type="password"
                  autoComplete="new-password"
                  {...p}
                  {...password.register("new_password")}
                />
              )}
            </Field>
            <Field label="Confirm new password" error={password.formState.errors.confirm?.message}>
              {(p) => (
                <Input
                  type="password"
                  autoComplete="new-password"
                  {...p}
                  {...password.register("confirm")}
                />
              )}
            </Field>
            <div>
              <Button type="submit" disabled={password.formState.isSubmitting}>
                Change password
              </Button>
            </div>
          </form>
        </Card>
      </div>
    </main>
  );
}
