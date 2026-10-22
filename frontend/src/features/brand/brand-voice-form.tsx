"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Controller, useFieldArray, useForm, useWatch } from "react-hook-form";
import { z } from "zod";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Textarea } from "@/components/ui/input";
import { PageLoading } from "@/components/ui/spinner";
import { TagInput } from "@/components/ui/tag-input";
import { useToast } from "@/components/ui/toast";
import { useOrg } from "@/hooks/use-org";
import { type BrandGuideline, updateBrandGuideline } from "@/lib/api/brand";
import { applyServerErrors } from "@/lib/validation/forms";
import { zodResolver } from "@/lib/validation/zod-resolver";

import { brandDependents, brandKeys, useBrandGuideline } from "./queries";

const HEX = /^#[0-9a-fA-F]{6}$/;
const schema = z.object({
  tone: z.array(z.string()).max(8),
  voice_description: z.string().trim().max(2000),
  do_list: z.array(z.string()).max(20),
  dont_list: z.array(z.string()).max(20),
  restricted_claims: z.array(z.string()).max(30),
  example_posts: z.array(z.object({ text: z.string().trim().max(2200) })).max(10),
  colors: z.array(z.string().regex(HEX, "Use hex colours like #1A2B3C")).max(10),
  fonts: z.array(z.string()).max(5),
});
type Values = z.infer<typeof schema>;

const TONE_SUGGESTIONS = [
  "Friendly",
  "Professional",
  "Playful",
  "Warm",
  "Expert",
  "Bold",
  "Calm",
  "Witty",
];

function toValues(g: BrandGuideline): Values {
  return {
    ...g,
    example_posts: g.example_posts.map((text) => ({ text })),
  };
}

export function BrandVoiceForm({
  onSaved,
  submitLabel = "Save",
}: {
  onSaved?: () => void;
  submitLabel?: string;
}) {
  const guideline = useBrandGuideline();
  if (guideline.isPending) return <PageLoading />;
  if (!guideline.data)
    return <Alert tone="danger">Couldn&apos;t load your brand guidelines.</Alert>;
  return <Inner initial={toValues(guideline.data)} onSaved={onSaved} submitLabel={submitLabel} />;
}

function Inner({
  initial,
  onSaved,
  submitLabel,
}: {
  initial: Values;
  onSaved?: () => void;
  submitLabel: string;
}) {
  const { organization, can } = useOrg();
  const queryClient = useQueryClient();
  const toast = useToast();
  const [formError, setFormError] = useState<string | null>(null);
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: initial });
  const examples = useFieldArray({ control: form.control, name: "example_posts" });
  const colors = useWatch({ control: form.control, name: "colors" });
  const readOnly = !can("brand.edit");
  const { errors } = form.formState;

  const onSubmit = form.handleSubmit(async (values) => {
    setFormError(null);
    try {
      const saved = await updateBrandGuideline(organization.id, {
        ...values,
        example_posts: values.example_posts.map((e) => e.text).filter(Boolean),
      });
      queryClient.setQueryData(brandKeys.guideline(organization.id), saved);
      await Promise.all(
        brandDependents(organization.id).map((k) => queryClient.invalidateQueries({ queryKey: k })),
      );
      form.reset(toValues(saved));
      toast("Brand voice saved.");
      onSaved?.();
    } catch (error) {
      setFormError(applyServerErrors(error, form.setError, Object.keys(schema.shape)));
    }
  });

  const tagField = (
    name: "tone" | "do_list" | "dont_list" | "restricted_claims" | "fonts" | "colors",
    label: string,
    hint: string,
    maxItems: number,
  ) => (
    <Controller
      control={form.control}
      name={name}
      render={({ field }) => (
        <Field
          label={label}
          optional
          hint={hint}
          error={
            errors[name]?.message ??
            (Array.isArray(errors[name])
              ? (errors[name] as { message?: string }[]).find(Boolean)?.message
              : undefined)
          }
        >
          {(p) => (
            <TagInput
              {...p}
              value={field.value}
              onChange={field.onChange}
              maxItems={maxItems}
              disabled={readOnly}
            />
          )}
        </Field>
      )}
    />
  );

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-5">
      {formError && <Alert tone="danger">{formError}</Alert>}
      {tagField(
        "tone",
        "Tone of voice",
        `Adjectives, e.g. ${TONE_SUGGESTIONS.slice(0, 4).join(", ")}.`,
        8,
      )}
      <Field label="Describe how you sound" optional>
        {(p) => (
          <Textarea
            rows={3}
            placeholder="e.g. We talk like a knowledgeable friend: helpful, never pushy, a little humour."
            {...p}
            disabled={readOnly}
            {...form.register("voice_description")}
          />
        )}
      </Field>
      <div className="grid gap-5 sm:grid-cols-2">
        {tagField("do_list", "Always", "Things your content should do.", 20)}
        {tagField("dont_list", "Never", "Things your content must avoid.", 20)}
      </div>
      {tagField(
        "restricted_claims",
        "Claims you must not make",
        "e.g. 'Guaranteed results', medical claims, prices that change often. AI output is checked against these.",
        30,
      )}

      <fieldset className="flex flex-col gap-3" disabled={readOnly}>
        <legend className="text-sm font-medium">
          Example posts you like <span className="font-normal text-muted">(optional)</span>
        </legend>
        {examples.fields.map((f, i) => (
          <div key={f.id} className="flex gap-2">
            <Textarea
              rows={3}
              aria-label={`Example post ${i + 1}`}
              {...form.register(`example_posts.${i}.text`)}
            />
            <Button variant="ghost" size="sm" onClick={() => examples.remove(i)}>
              Remove
            </Button>
          </div>
        ))}
        {!readOnly && examples.fields.length < 10 && (
          <div>
            <Button variant="secondary" size="sm" onClick={() => examples.append({ text: "" })}>
              + Add example
            </Button>
          </div>
        )}
      </fieldset>

      <div className="grid gap-5 sm:grid-cols-2">
        <div className="flex flex-col gap-2">
          {tagField("colors", "Brand colours", "Hex codes, e.g. #4338CA.", 10)}
          <div className="flex gap-1.5" aria-hidden>
            {colors
              .filter((c) => HEX.test(c))
              .map((c) => (
                <span
                  key={c}
                  className="size-6 rounded border border-border"
                  style={{ background: c }}
                />
              ))}
          </div>
        </div>
        {tagField("fonts", "Fonts", "Font names used in your materials.", 5)}
      </div>

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
