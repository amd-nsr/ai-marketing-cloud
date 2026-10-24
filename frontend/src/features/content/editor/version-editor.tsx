"use client";

import { type SyntheticEvent, useRef, useState } from "react";
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
import { useStudioCapabilities } from "../studio/queries";
import { type AssistField, WritingAssistant } from "../studio/writing-assistant";
import { useRefreshItem } from "./queries";

const EDITABLE = new Set(["draft", "in_review", "changes_requested", "approved"]);

type TextFields = Omit<VersionFields, "document">;
type TextField = "hook" | "headline" | "caption" | "cta" | "script" | `slides.${number}.body`;

function toValues(item: ContentItem): TextFields {
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

/** Field labels differ per channel: an email has a subject line, a blog an article body. */
function labelsFor(platform: ContentItem["platform"]) {
  if (platform === "email")
    return {
      headline: "Subject line",
      hook: "Preview text",
      caption: "Email body",
      cta: "Call to action",
      hookHint: "Shown next to the subject in the inbox.",
    };
  if (platform === "blog")
    return {
      headline: "Article title",
      hook: "Introduction",
      caption: "Article body",
      cta: "Call to action",
      hookHint: "The opening paragraph or summary.",
    };
  return {
    headline: "Headline",
    hook: "Hook",
    caption: "Caption",
    cta: "Call to action",
    hookHint: "The first line or first second.",
  };
}

export function VersionEditor({ item }: { item: ContentItem }) {
  const { organization, can } = useOrg();
  const toast = useToast();
  const refresh = useRefreshItem();
  const caps = useStudioCapabilities();
  const [error, setError] = useState<string | null>(null);
  const [assistField, setAssistField] = useState<AssistField>({
    name: "caption",
    kind: "caption",
    label: labelsFor(item.platform).caption,
  });
  const selection = useRef<Record<string, [number, number]>>({});
  const form = useForm<TextFields>({ values: toValues(item) });
  const slides = useFieldArray({ control: form.control, name: "slides" });
  const caption = useWatch({ control: form.control, name: "caption" }) ?? "";
  const hashtags = useWatch({ control: form.control, name: "hashtags" }) ?? [];

  const editable = can("content.edit") && EDITABLE.has(item.status);
  const aiReady = editable && caps.data?.text_generation.available !== false;
  const longForm = item.platform === "blog" || item.platform === "email";
  const labels = labelsFor(item.platform);
  const limit = CAPTION_LIMIT[item.platform];
  const length = caption.length + hashtags.reduce((n, h) => n + h.length + 2, 0);
  const video = item.format === "reel" || item.format === "short_video";
  const resetsReview =
    item.status === "in_review" ||
    item.status === "approved" ||
    item.status === "changes_requested";

  const trackSelection =
    (name: string) => (e: SyntheticEvent<HTMLInputElement | HTMLTextAreaElement>) => {
      const el = e.currentTarget;
      selection.current[name] = [el.selectionStart ?? 0, el.selectionEnd ?? 0];
    };

  const assistFields: AssistField[] = [
    { name: "caption", kind: "caption", label: labels.caption },
    { name: "hook", kind: "hook", label: labels.hook },
    { name: "headline", kind: "headline", label: labels.headline },
    { name: "cta", kind: "cta", label: labels.cta },
    ...(video ? [{ name: "script", kind: "script", label: "Video script" }] : []),
    ...slides.fields.map((_, i) => ({
      name: `slides.${i}.body`,
      kind: "slide",
      label: `Slide ${i + 1} text`,
    })),
  ];
  const textOf = (name: string) => String(form.getValues(name as TextField) ?? "");
  const selectionOf = (name: string) => {
    const [start, end] = selection.current[name] ?? [0, 0];
    const full = textOf(name);
    return end > start && end - start < full.length ? { start, end } : null;
  };
  const applySuggestion = (
    field: AssistField,
    text: string,
    mode: "replace" | "append",
    range?: { start: number; end: number },
  ) => {
    const name = field.name as TextField;
    const full = textOf(name);
    const next = range
      ? full.slice(0, range.start) + text + full.slice(range.end)
      : mode === "append" && full.trim()
        ? `${full.trimEnd()}\n\n${text}`
        : text;
    form.setValue(name, next, { shouldDirty: true });
    delete selection.current[name];
    toast("Added to the editor. Save to keep it.");
  };
  const addHashtag = (raw: string) => {
    const tag = `#${raw.replace(/^#/, "").replace(/\s+/g, "")}`;
    const current = form.getValues("hashtags");
    if (!current.some((t) => t.toLowerCase() === tag.toLowerCase()))
      form.setValue("hashtags", [...current, tag], { shouldDirty: true });
  };

  const assistButton = (name: TextField, label: string) =>
    aiReady ? (
      <button
        type="button"
        onClick={() => {
          setAssistField({ name, kind: name.startsWith("slides") ? "slide" : name, label });
          document.getElementById("writing-assistant")?.scrollIntoView({ block: "nearest" });
        }}
        className={cn(
          "self-start text-xs font-medium hover:underline",
          assistField.name === name ? "text-foreground" : "text-primary",
        )}
        aria-label={`Use the AI assistant on ${label}`}
      >
        {assistField.name === name ? "AI assistant is on this field" : "AI assist"}
      </button>
    ) : null;

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
    <div className="grid gap-6 lg:grid-cols-[1fr_20rem]">
      <form onSubmit={save} className="flex min-w-0 flex-col gap-4">
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
            <div className="flex flex-col gap-1">
              <Field label={labels.headline} optional={item.platform !== "email"}>
                {(p) => (
                  <Input
                    {...p}
                    {...form.register("headline")}
                    onSelect={trackSelection("headline")}
                  />
                )}
              </Field>
              {assistButton("headline", labels.headline)}
            </div>
            <div className="flex flex-col gap-1">
              <Field label={labels.hook} optional hint={labels.hookHint}>
                {(p) =>
                  longForm ? (
                    <Textarea
                      rows={2}
                      {...p}
                      {...form.register("hook")}
                      onSelect={trackSelection("hook")}
                    />
                  ) : (
                    <Input {...p} {...form.register("hook")} onSelect={trackSelection("hook")} />
                  )
                }
              </Field>
              {assistButton("hook", labels.hook)}
            </div>
          </div>
          <div className="flex flex-col gap-1">
            <Field
              label={labels.caption}
              hint={
                <span className={cn(length > limit && "font-medium text-danger")}>
                  {length.toLocaleString()} / {limit.toLocaleString()} characters
                  {longForm ? "" : " including hashtags"}
                  {item.platform === "blog" && " · Markdown headings and lists are fine."}
                  {" · Select part of the text to work on just that part."}
                </span>
              }
            >
              {(p) => (
                <Textarea
                  rows={longForm ? 16 : 8}
                  {...p}
                  {...form.register("caption")}
                  onSelect={trackSelection("caption")}
                />
              )}
            </Field>
            {assistButton("caption", labels.caption)}
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="flex flex-col gap-1">
              <Field label={labels.cta} optional>
                {(p) => <Input {...p} {...form.register("cta")} onSelect={trackSelection("cta")} />}
              </Field>
              {assistButton("cta", labels.cta)}
            </div>
            {!longForm && (
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
            )}
          </div>
          {video && (
            <div className="flex flex-col gap-1">
              <Field
                label="Video script"
                hint="Shots, on-screen text, and voiceover. The Video tab can plan a storyboard."
              >
                {(p) => (
                  <Textarea
                    rows={6}
                    {...p}
                    {...form.register("script")}
                    onSelect={trackSelection("script")}
                  />
                )}
              </Field>
              {assistButton("script", "Video script")}
            </div>
          )}
          {item.format === "carousel" && (
            <fieldset className="flex flex-col gap-2">
              <legend className="mb-1 text-sm font-medium">Slide copy</legend>
              <p className="text-xs text-muted">
                The outline for each slide. In the Carousel tab, “Build from slide copy” lays these
                out as editable slides.
              </p>
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
                  <Input
                    aria-label={`Slide ${i + 1} text`}
                    {...form.register(`slides.${i}.body`)}
                    onSelect={trackSelection(`slides.${i}.body`)}
                  />
                  <div className="flex items-center gap-1">
                    {aiReady && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() =>
                          setAssistField({
                            name: `slides.${i}.body`,
                            kind: "slide",
                            label: `Slide ${i + 1} text`,
                          })
                        }
                      >
                        AI
                      </Button>
                    )}
                    <Button variant="ghost" size="sm" onClick={() => slides.remove(i)}>
                      Remove
                    </Button>
                  </div>
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
          {!longForm && (
            <>
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
            </>
          )}
        </fieldset>
        {editable && (
          <div className="flex flex-wrap items-center justify-end gap-3">
            {resetsReview && form.formState.isDirty && (
              <p className="text-xs text-warning">
                Saving returns this to draft and needs a new approval.
              </p>
            )}
            {form.formState.isDirty && (
              <Button variant="ghost" onClick={() => form.reset(toValues(item))}>
                Discard changes
              </Button>
            )}
            <Button type="submit" disabled={!form.formState.isDirty || form.formState.isSubmitting}>
              {form.formState.isSubmitting ? "Saving…" : "Save new version"}
            </Button>
          </div>
        )}
      </form>
      {aiReady && (
        <aside
          id="writing-assistant"
          aria-label="AI writing assistant"
          className="self-start rounded-lg border border-border bg-neutral-soft/50 p-4 lg:sticky lg:top-4"
        >
          <h2 className="mb-3 text-sm font-semibold">AI writing assistant</h2>
          <WritingAssistant
            itemId={item.id}
            fields={assistFields}
            field={assistFields.find((f) => f.name === assistField.name) ?? assistFields[0]}
            onFieldChange={setAssistField}
            getText={textOf}
            getSelection={selectionOf}
            onApply={applySuggestion}
            onHashtag={addHashtag}
            allowHashtags={!longForm}
          />
        </aside>
      )}
    </div>
  );
}
