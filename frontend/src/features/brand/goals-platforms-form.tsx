"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { CheckboxGroup } from "@/components/ui/checkbox-group";
import { Field } from "@/components/ui/field";
import { PageLoading } from "@/components/ui/spinner";
import { TagInput } from "@/components/ui/tag-input";
import { useToast } from "@/components/ui/toast";
import { useOrg } from "@/hooks/use-org";
import {
  type BusinessProfile,
  type Platform,
  type ReferenceData,
  updateBusinessProfile,
} from "@/lib/api/brand";
import { applyServerErrors } from "@/lib/validation/forms";
import { zodResolver } from "@/lib/validation/zod-resolver";

import { brandDependents, brandKeys, useBusinessProfile, useReferenceData } from "./queries";

const schema = z.object({
  goals: z.array(z.string()).min(1, "Choose at least one goal."),
  custom_goals: z.array(z.string()),
  preferred_platforms: z
    .array(z.enum(["instagram", "facebook", "tiktok"]))
    .min(1, "Choose at least one platform."),
  languages: z.array(
    z.string().regex(/^[a-z]{2,3}(-[A-Za-z]{2,4})?$/, "Use language codes like en or ar"),
  ),
});
type Values = z.infer<typeof schema>;

export function GoalsPlatformsForm({
  onSaved,
  submitLabel = "Save",
}: {
  onSaved?: () => void;
  submitLabel?: string;
}) {
  const profile = useBusinessProfile();
  const reference = useReferenceData();
  if (profile.isPending || reference.isPending) return <PageLoading />;
  if (!profile.data || !reference.data)
    return <Alert tone="danger">Couldn&apos;t load your goals.</Alert>;
  return (
    <Inner
      profile={profile.data}
      reference={reference.data}
      onSaved={onSaved}
      submitLabel={submitLabel}
    />
  );
}

function Inner({
  profile,
  reference,
  onSaved,
  submitLabel,
}: {
  profile: BusinessProfile;
  reference: ReferenceData;
  onSaved?: () => void;
  submitLabel: string;
}) {
  const { organization, can } = useOrg();
  const queryClient = useQueryClient();
  const toast = useToast();
  const [formError, setFormError] = useState<string | null>(null);
  const preset = reference.industries.find((i) => i.key === profile.industry);
  const known = Object.keys(reference.goals);
  const isNew = profile.goals.length === 0 && profile.preferred_platforms.length === 0;
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      goals:
        isNew && preset ? preset.suggested_goals : profile.goals.filter((g) => known.includes(g)),
      custom_goals: profile.goals.filter((g) => !known.includes(g)),
      preferred_platforms:
        isNew && preset ? (preset.suggested_platforms as Platform[]) : profile.preferred_platforms,
      languages: profile.languages.length ? profile.languages : ["en"],
    },
  });
  const readOnly = !can("brand.edit");
  const { errors } = form.formState;

  const onSubmit = form.handleSubmit(async (values) => {
    setFormError(null);
    try {
      const saved = await updateBusinessProfile(organization.id, {
        goals: [...values.goals, ...values.custom_goals],
        preferred_platforms: values.preferred_platforms,
        languages: values.languages,
      });
      queryClient.setQueryData(brandKeys.profile(organization.id), saved);
      await Promise.all(
        brandDependents(organization.id).map((k) => queryClient.invalidateQueries({ queryKey: k })),
      );
      toast("Goals and platforms saved.");
      onSaved?.();
    } catch (error) {
      setFormError(
        applyServerErrors(error, form.setError, ["goals", "preferred_platforms", "languages"]),
      );
    }
  });

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-6">
      {formError && <Alert tone="danger">{formError}</Alert>}
      {isNew && preset && (
        <Alert tone="info">
          Pre-selected from common choices for {preset.label.toLowerCase()}. Adjust to fit your
          business.
        </Alert>
      )}
      <Controller
        control={form.control}
        name="goals"
        render={({ field }) => (
          <CheckboxGroup
            legend="What should marketing achieve?"
            options={Object.entries(reference.goals).map(([value, label]) => ({
              value,
              label,
              hint: preset?.suggested_goals.includes(value)
                ? "Common for your industry"
                : undefined,
            }))}
            value={field.value}
            onChange={field.onChange}
            error={errors.goals?.message}
            disabled={readOnly}
          />
        )}
      />
      <Controller
        control={form.control}
        name="custom_goals"
        render={({ field }) => (
          <Field label="Other goals" optional hint="Press Enter after each goal.">
            {(p) => (
              <TagInput
                {...p}
                value={field.value}
                onChange={field.onChange}
                maxItems={5}
                disabled={readOnly}
              />
            )}
          </Field>
        )}
      />
      <Controller
        control={form.control}
        name="preferred_platforms"
        render={({ field }) => (
          <CheckboxGroup
            legend="Where do you want to publish?"
            columns={3}
            options={Object.entries(reference.platforms).map(([value, label]) => ({
              value,
              label,
            }))}
            value={field.value}
            onChange={field.onChange}
            error={errors.preferred_platforms?.message}
            disabled={readOnly}
          />
        )}
      />
      <Controller
        control={form.control}
        name="languages"
        render={({ field }) => (
          <Field
            label="Content languages"
            hint="Language codes, e.g. en, ar, fr. Press Enter after each."
            error={
              errors.languages?.message ??
              (Array.isArray(errors.languages)
                ? errors.languages.find(Boolean)?.message
                : undefined)
            }
          >
            {(p) => (
              <TagInput
                {...p}
                value={field.value}
                onChange={field.onChange}
                maxItems={5}
                maxLength={10}
                disabled={readOnly}
              />
            )}
          </Field>
        )}
      />
      {!readOnly && (
        <div>
          <Button type="submit" disabled={form.formState.isSubmitting}>
            {form.formState.isSubmitting ? "Saving…" : submitLabel}
          </Button>
        </div>
      )}
    </form>
  );
}
