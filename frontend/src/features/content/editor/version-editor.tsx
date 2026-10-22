"use client";

import { useState } from "react";
import { Controller, useFieldArray, useForm, useWatch } from "react-hook-form";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { TagInput } from "@/components/ui/tag-input";
import { useToast } from "@/components/ui/toast";
import { useOrg } from "@/hooks/use-org";
import { type ContentItem, createVersion, type VersionFields } from "@/lib/api/content";
import { errorMessage } from "@/lib/api/errors";
import { cn } from "@/lib/utils";

import { CAPTION_LIMIT } from "../labels";
import { useRefreshItem } from "./queries";

const EDITABLE = new Set(["draft", "in_review", "changes_requested", "approved"]);

function toValues(item: ContentItem): VersionFields {
  const v = item.current_version;
  return {
    headline: v?.headline ?? "",
    hook: v?.hook ?? "",
    caption: v?.caption ?? "",
    cta: v?.cta ?? "",
    hashtags: v?.hashtags ?? [],
    script: v?.script ?? "",
    slides: v?.slides ?? [],
    creative_brief: v?.creative_brief ?? "",
    alt_text: v?.alt_text ?? "",
  };
}

export function VersionEditor({ item }: { item: ContentItem }) {
  const { organization, can } = useOrg();
  const toast = useToast();
  const refresh = useRefreshItem();
  const [error, setError] = useState<string | null>(null);
  const form = useForm<VersionFields>({ values: toValues(item) });
  const slides = useFieldArray({ control: form.control, name: "slides" });
  const caption = useWatch({ control: form.control, name: "caption" }) ?? "";
  const hashtags = useWatch({ control: form.control, name: "hashtags" }) ?? [];

  const editable = can("content.edit") && EDITABLE.has(item.status);
  const limit = CAPTION_LIMIT[item.platform];
  const length = caption.length + hashtags.reduce((n, h) => n + h.length + 2, 0);
  const video = item.format === "reel" || item.format === "short_video";
  const resetsReview =
    item.status === "in_review" ||
    item.status === "approved" ||
    item.status === "changes_requested";

  const save = form.handleSubmit(async (values) => {
    setError(null);
    try {
      const version = await createVersion(organization.id, item.id, values);
      await refresh();
      toast(`Saved as version ${version.number}.`);
    } catch (e) {
      setError(errorMessage(e));
    }
  });

  return (
    <form onSubmit={save} className="flex flex-col gap-4">
      {!editable && item.status !== "archived" && (
        <Alert tone="info">
          {can("content.edit")
            ? "This content is scheduled or published, so its text is locked."
            : "You can view this content but not edit it."}
        </Alert>
      )}
      {error && <Alert tone="danger">{error}</Alert>}
      <fieldset disabled={!editable} className="flex flex-col gap-4">
        <div className="grid gap-4 md:grid-cols-2">
          <Field label="Hook" optional hint="The first line or first second.">
            {(p) => <Input {...p} {...form.register("hook")} />}
          </Field>
          <Field label="Headline" optional>
            {(p) => <Input {...p} {...form.register("headline")} />}
          </Field>
        </div>
        <Field
          label="Caption"
          hint={
            <span className={cn(length > limit && "font-medium text-danger")}>
              {length.toLocaleString()} / {limit.toLocaleString()} characters including hashtags
            </span>
          }
        >
          {(p) => <Textarea rows={8} {...p} {...form.register("caption")} />}
        </Field>
        <div className="grid gap-4 md:grid-cols-2">
          <Field label="Call to action" optional>
            {(p) => <Input {...p} {...form.register("cta")} />}
          </Field>
          <Controller
            control={form.control}
            name="hashtags"
            render={({ field }) => (
              <Field label="Hashtags" optional hint="Press Enter after each.">
                {(p) => (
                  <TagInput
                    {...p}
                    value={field.value}
                    onChange={field.onChange}
                    maxItems={30}
                    maxLength={100}
                    disabled={!editable}
                  />
                )}
              </Field>
            )}
          />
        </div>
        {video && (
          <Field label="Video script" hint="Shots, on-screen text, and voiceover.">
            {(p) => <Textarea rows={6} {...p} {...form.register("script")} />}
          </Field>
        )}
        {item.format === "carousel" && (
          <fieldset className="flex flex-col gap-2">
            <legend className="mb-1 text-sm font-medium">Slides</legend>
            {slides.fields.map((f, i) => (
              <div
                key={f.id}
                className="grid gap-2 rounded-md border border-border p-3 md:grid-cols-[12rem_1fr_auto]"
              >
                <Input
                  aria-label={`Slide ${i + 1} title`}
                  placeholder={`Slide ${i + 1}`}
                  {...form.register(`slides.${i}.title`)}
                />
                <Input aria-label={`Slide ${i + 1} text`} {...form.register(`slides.${i}.body`)} />
                <Button variant="ghost" size="sm" onClick={() => slides.remove(i)}>
                  Remove
                </Button>
              </div>
            ))}
            {editable && slides.fields.length < 20 && (
              <div>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => slides.append({ title: "", body: "" })}
                >
                  + Add slide
                </Button>
              </div>
            )}
          </fieldset>
        )}
        <Field label="Creative brief" optional hint="What visual to create or pick.">
          {(p) => <Textarea rows={3} {...p} {...form.register("creative_brief")} />}
        </Field>
        <Field
          label="Alt text"
          optional
          hint="Describes the image for people using screen readers."
        >
          {(p) => <Input {...p} {...form.register("alt_text")} />}
        </Field>
      </fieldset>
      {editable && (
        <div className="flex flex-wrap items-center justify-end gap-3">
          {resetsReview && form.formState.isDirty && (
            <p className="text-xs text-warning">
              Saving returns this to draft and needs a new approval.
            </p>
          )}
          <Button type="submit" disabled={!form.formState.isDirty || form.formState.isSubmitting}>
            {form.formState.isSubmitting ? "Saving…" : "Save new version"}
          </Button>
        </div>
      )}
    </form>
  );
}
