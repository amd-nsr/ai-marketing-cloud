"use client";

import { useState } from "react";
import { useFieldArray, useForm } from "react-hook-form";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import type { Plan, PlanContent } from "@/lib/api/marketing";

/**
 * Edits the most commonly changed parts of a plan. Saving creates a new version;
 * sections not shown here are carried over unchanged.
 */
export function PlanEditor({
  plan,
  onSave,
  onCancel,
}: {
  plan: Plan;
  onSave: (content: PlanContent) => Promise<void>;
  onCancel: () => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const form = useForm<PlanContent>({ defaultValues: structuredClone(plan.content) });
  const objectives = useFieldArray({ control: form.control, name: "objectives" });
  const themes = useFieldArray({ control: form.control, name: "content_themes" });
  const concepts = useFieldArray({ control: form.control, name: "campaign_concepts" });
  const calendar = useFieldArray({ control: form.control, name: "content_calendar" });

  const submit = form.handleSubmit(async (values) => {
    setError(null);
    try {
      await onSave(values);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save.");
    }
  });

  return (
    <form onSubmit={submit} className="flex flex-col gap-8">
      <Alert tone="info">
        Saving creates version {plan.version + 1}. Version {plan.version} stays in the history.
      </Alert>
      {error && <Alert tone="danger">{error}</Alert>}

      <div className="flex flex-col gap-4">
        <Field label="Title">
          {(p) => <Input {...p} {...form.register("title", { required: true })} />}
        </Field>
        <Field label="Summary">
          {(p) => <Textarea rows={4} {...p} {...form.register("summary")} />}
        </Field>
      </div>

      <fieldset className="flex flex-col gap-3">
        <legend className="mb-2 text-sm font-semibold">Objectives</legend>
        {objectives.fields.map((f, i) => (
          <div key={f.id} className="grid gap-2 rounded-lg border border-border p-3 md:grid-cols-2">
            <Input aria-label="Objective title" {...form.register(`objectives.${i}.title`)} />
            <Input
              aria-label="Metric"
              placeholder="Metric"
              {...form.register(`objectives.${i}.metric`)}
            />
            <Textarea
              aria-label="Description"
              rows={2}
              className="md:col-span-2"
              {...form.register(`objectives.${i}.description`)}
            />
            <Input
              aria-label="Target"
              placeholder="Target (hypothesis)"
              {...form.register(`objectives.${i}.target`)}
            />
            <div className="flex gap-2">
              <Input
                aria-label="Timeframe"
                placeholder="Timeframe"
                {...form.register(`objectives.${i}.timeframe`)}
              />
              <Button variant="ghost" size="sm" onClick={() => objectives.remove(i)}>
                Remove
              </Button>
            </div>
          </div>
        ))}
        <div>
          <Button
            variant="secondary"
            size="sm"
            onClick={() =>
              objectives.append({
                title: "",
                description: "",
                metric: "",
                target: "",
                timeframe: "",
              })
            }
          >
            + Add objective
          </Button>
        </div>
      </fieldset>

      <fieldset className="flex flex-col gap-3">
        <legend className="mb-2 text-sm font-semibold">Content themes</legend>
        {themes.fields.map((f, i) => (
          <div
            key={f.id}
            className="grid gap-2 rounded-lg border border-border p-3 md:grid-cols-[14rem_1fr_auto]"
          >
            <Input aria-label="Theme name" {...form.register(`content_themes.${i}.name`)} />
            <Input
              aria-label="Theme description"
              {...form.register(`content_themes.${i}.description`)}
            />
            <Button variant="ghost" size="sm" onClick={() => themes.remove(i)}>
              Remove
            </Button>
          </div>
        ))}
        <div>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => themes.append({ name: "", description: "", example_ideas: [] })}
          >
            + Add theme
          </Button>
        </div>
      </fieldset>

      <fieldset className="flex flex-col gap-3">
        <legend className="mb-2 text-sm font-semibold">Campaign concepts</legend>
        {concepts.fields.map((f, i) => (
          <div key={f.id} className="flex flex-col gap-2 rounded-lg border border-border p-3">
            <div className="flex gap-2">
              <Input aria-label="Campaign name" {...form.register(`campaign_concepts.${i}.name`)} />
              <Button variant="ghost" size="sm" onClick={() => concepts.remove(i)}>
                Remove
              </Button>
            </div>
            <Textarea
              aria-label="Campaign description"
              rows={2}
              {...form.register(`campaign_concepts.${i}.description`)}
            />
          </div>
        ))}
      </fieldset>

      <fieldset className="flex flex-col gap-2">
        <legend className="mb-2 text-sm font-semibold">Calendar ideas</legend>
        {calendar.fields.map((f, i) => (
          <div key={f.id} className="grid items-center gap-2 md:grid-cols-[9rem_1fr_auto]">
            <span className="text-xs text-muted">
              Week {f.week} · {f.day} · {f.platform}
            </span>
            <Input
              aria-label={`Idea for week ${f.week} ${f.day}`}
              {...form.register(`content_calendar.${i}.idea`)}
            />
            <Button variant="ghost" size="sm" onClick={() => calendar.remove(i)}>
              Remove
            </Button>
          </div>
        ))}
      </fieldset>

      <div className="sticky bottom-0 flex justify-end gap-2 border-t border-border bg-surface py-3">
        <Button variant="secondary" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" disabled={form.formState.isSubmitting}>
          {form.formState.isSubmitting ? "Saving…" : "Save as new version"}
        </Button>
      </div>
    </form>
  );
}
