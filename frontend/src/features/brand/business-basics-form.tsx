"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Controller, useFieldArray, useForm, useWatch } from "react-hook-form";
import { z } from "zod";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input, Select, Textarea } from "@/components/ui/input";
import { PageLoading } from "@/components/ui/spinner";
import { useToast } from "@/components/ui/toast";
import { useOrg } from "@/hooks/use-org";
import { type BusinessProfile, updateBusinessProfile } from "@/lib/api/brand";
import { applyServerErrors } from "@/lib/validation/forms";
import { zodResolver } from "@/lib/validation/zod-resolver";

import { brandDependents, brandKeys, useBusinessProfile, useReferenceData } from "./queries";

const schema = z.object({
  business_name: z.string().trim().min(1, "Enter your business name.").max(160),
  industry: z.string().min(1, "Choose the closest industry."),
  website: z.union([
    z.literal(""),
    z.string().trim().url("Enter a full URL, e.g. https://example.com"),
  ]),
  description: z.string().trim().min(10, "Describe your business in a sentence or two.").max(4000),
  location: z.string().trim().max(200),
  service_area: z.string().trim().max(300),
  products_services: z
    .array(
      z.object({
        name: z.string().trim().min(1, "Name required").max(120),
        description: z.string().trim().max(500),
      }),
    )
    .max(30),
});
type Values = z.infer<typeof schema>;

function toValues(p: BusinessProfile): Values {
  return {
    business_name: p.business_name,
    industry: p.industry,
    website: p.website,
    description: p.description,
    location: p.location,
    service_area: p.service_area,
    products_services: p.products_services,
  };
}

export function BusinessBasicsForm({
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
    return <Alert tone="danger">Couldn&apos;t load your business profile.</Alert>;
  return (
    <BasicsInner
      initial={toValues(profile.data)}
      industries={reference.data.industries}
      onSaved={onSaved}
      submitLabel={submitLabel}
    />
  );
}

function BasicsInner({
  initial,
  industries,
  onSaved,
  submitLabel,
}: {
  initial: Values;
  industries: { key: string; label: string; compliance_notes: string[] }[];
  onSaved?: () => void;
  submitLabel: string;
}) {
  const { organization, can } = useOrg();
  const queryClient = useQueryClient();
  const toast = useToast();
  const [formError, setFormError] = useState<string | null>(null);
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: initial });
  const products = useFieldArray({ control: form.control, name: "products_services" });
  const industry = useWatch({ control: form.control, name: "industry" });
  const preset = industries.find((i) => i.key === industry);
  const readOnly = !can("brand.edit");
  const { errors } = form.formState;

  const onSubmit = form.handleSubmit(async (values) => {
    setFormError(null);
    try {
      const saved = await updateBusinessProfile(organization.id, values);
      queryClient.setQueryData(brandKeys.profile(organization.id), saved);
      await Promise.all(
        brandDependents(organization.id).map((k) => queryClient.invalidateQueries({ queryKey: k })),
      );
      form.reset(toValues(saved));
      toast("Business details saved.");
      onSaved?.();
    } catch (error) {
      setFormError(applyServerErrors(error, form.setError, Object.keys(schema.shape)));
    }
  });

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-5">
      {formError && <Alert tone="danger">{formError}</Alert>}
      <div className="grid gap-5 sm:grid-cols-2">
        <Field label="Business name" error={errors.business_name?.message}>
          {(p) => <Input {...p} disabled={readOnly} {...form.register("business_name")} />}
        </Field>
        <Field label="Industry" error={errors.industry?.message}>
          {(p) => (
            <Select {...p} disabled={readOnly} {...form.register("industry")}>
              <option value="">Choose…</option>
              {industries.map((i) => (
                <option key={i.key} value={i.key}>
                  {i.label}
                </option>
              ))}
            </Select>
          )}
        </Field>
      </div>
      {preset && preset.compliance_notes.length > 0 && (
        <Alert tone="info" title="Good to know for this industry">
          {preset.compliance_notes.join(" ")} You can add your own restrictions under Brand voice.
        </Alert>
      )}
      <Field
        label="What does your business do?"
        error={errors.description?.message}
        hint="Plain facts work best. The AI uses this as ground truth and won't invent other details."
      >
        {(p) => <Textarea rows={4} {...p} disabled={readOnly} {...form.register("description")} />}
      </Field>
      <div className="grid gap-5 md:grid-cols-3">
        <Field label="Website" optional error={errors.website?.message}>
          {(p) => (
            <Input
              type="url"
              placeholder="https://"
              {...p}
              disabled={readOnly}
              {...form.register("website")}
            />
          )}
        </Field>
        <Field label="Location" optional error={errors.location?.message}>
          {(p) => (
            <Input
              placeholder="City, country"
              {...p}
              disabled={readOnly}
              {...form.register("location")}
            />
          )}
        </Field>
        <Field label="Service area" optional error={errors.service_area?.message}>
          {(p) => (
            <Input
              placeholder="e.g. Downtown and 10 km radius"
              {...p}
              disabled={readOnly}
              {...form.register("service_area")}
            />
          )}
        </Field>
      </div>

      <fieldset className="flex flex-col gap-3" disabled={readOnly}>
        <legend className="text-sm font-medium">
          Products or services <span className="font-normal text-muted">(optional)</span>
        </legend>
        {products.fields.map((field, index) => (
          <div
            key={field.id}
            className="grid gap-2 rounded-md border border-border p-3 md:grid-cols-[14rem_1fr_auto]"
          >
            <Controller
              control={form.control}
              name={`products_services.${index}.name`}
              render={({ field: f }) => <Input aria-label="Name" placeholder="Name" {...f} />}
            />
            <Controller
              control={form.control}
              name={`products_services.${index}.description`}
              render={({ field: f }) => (
                <Input aria-label="Short description" placeholder="Short description" {...f} />
              )}
            />
            <Button
              variant="ghost"
              size="sm"
              onClick={() => products.remove(index)}
              aria-label="Remove item"
            >
              Remove
            </Button>
            {errors.products_services?.[index]?.name && (
              <p className="text-xs text-danger md:col-span-3">
                {errors.products_services[index]?.name?.message}
              </p>
            )}
          </div>
        ))}
        {!readOnly && products.fields.length < 30 && (
          <div>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => products.append({ name: "", description: "" })}
            >
              + Add product or service
            </Button>
          </div>
        )}
      </fieldset>

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
