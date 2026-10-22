"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmDialog, Dialog } from "@/components/ui/dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { Field } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { PageLoading } from "@/components/ui/spinner";
import { TagInput } from "@/components/ui/tag-input";
import { useToast } from "@/components/ui/toast";
import { useOrg } from "@/hooks/use-org";
import { type Audience, createAudience, deleteAudience, updateAudience } from "@/lib/api/brand";
import { errorMessage } from "@/lib/api/errors";
import { applyServerErrors } from "@/lib/validation/forms";
import { zodResolver } from "@/lib/validation/zod-resolver";

import {
  brandDependents,
  brandKeys,
  useAudiences,
  useBusinessProfile,
  useReferenceData,
} from "./queries";

const schema = z.object({
  name: z.string().trim().min(1, "Give this audience a name.").max(120),
  description: z.string().trim().max(2000),
  age_range: z.string().trim().max(40),
  locations: z.string().trim().max(200),
  interests: z.array(z.string()).max(15),
  pain_points: z.array(z.string()).max(15),
  is_primary: z.boolean(),
});
type Values = z.infer<typeof schema>;

const empty: Values = {
  name: "",
  description: "",
  age_range: "",
  locations: "",
  interests: [],
  pain_points: [],
  is_primary: false,
};

function AudienceDialog({
  audience,
  open,
  onClose,
}: {
  audience: Audience | null;
  open: boolean;
  onClose: () => void;
}) {
  const { organization } = useOrg();
  const queryClient = useQueryClient();
  const toast = useToast();
  const [formError, setFormError] = useState<string | null>(null);
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    values: audience ? { ...empty, ...audience } : empty,
  });
  const { errors } = form.formState;

  const onSubmit = form.handleSubmit(async (values) => {
    setFormError(null);
    try {
      if (audience) await updateAudience(organization.id, audience.id, values);
      else await createAudience(organization.id, values);
      await Promise.all(
        [brandKeys.audiences(organization.id), ...brandDependents(organization.id)].map((k) =>
          queryClient.invalidateQueries({ queryKey: k }),
        ),
      );
      toast(audience ? "Audience updated." : "Audience added.");
      onClose();
    } catch (error) {
      setFormError(applyServerErrors(error, form.setError, Object.keys(schema.shape)));
    }
  });

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={audience ? "Edit audience" : "Add audience"}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={onSubmit} disabled={form.formState.isSubmitting}>
            Save audience
          </Button>
        </>
      }
    >
      <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
        {formError && <Alert tone="danger">{formError}</Alert>}
        <Field label="Name" error={errors.name?.message}>
          {(p) => (
            <Input
              placeholder="e.g. Young professionals nearby"
              {...p}
              {...form.register("name")}
            />
          )}
        </Field>
        <Field label="Who are they?" optional>
          {(p) => <Textarea rows={3} {...p} {...form.register("description")} />}
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Age range" optional>
            {(p) => <Input placeholder="25–40" {...p} {...form.register("age_range")} />}
          </Field>
          <Field label="Where" optional>
            {(p) => <Input {...p} {...form.register("locations")} />}
          </Field>
        </div>
        <Controller
          control={form.control}
          name="interests"
          render={({ field }) => (
            <Field label="Interests" optional hint="Press Enter after each.">
              {(p) => (
                <TagInput {...p} value={field.value} onChange={field.onChange} maxItems={15} />
              )}
            </Field>
          )}
        />
        <Controller
          control={form.control}
          name="pain_points"
          render={({ field }) => (
            <Field label="Problems you solve for them" optional hint="Press Enter after each.">
              {(p) => (
                <TagInput {...p} value={field.value} onChange={field.onChange} maxItems={15} />
              )}
            </Field>
          )}
        />
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            className="accent-[var(--primary)]"
            {...form.register("is_primary")}
          />
          Primary audience
        </label>
      </form>
    </Dialog>
  );
}

export function AudiencesEditor() {
  const { organization, can } = useOrg();
  const queryClient = useQueryClient();
  const toast = useToast();
  const audiences = useAudiences();
  const profile = useBusinessProfile();
  const reference = useReferenceData();
  const [editing, setEditing] = useState<Audience | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [deleting, setDeleting] = useState<Audience | null>(null);
  const canEdit = can("brand.edit");

  const invalidate = () =>
    Promise.all(
      [brandKeys.audiences(organization.id), ...brandDependents(organization.id)].map((k) =>
        queryClient.invalidateQueries({ queryKey: k }),
      ),
    );
  const quickAdd = useMutation({
    mutationFn: (name: string) => createAudience(organization.id, { name, is_primary: false }),
    onSuccess: invalidate,
    onError: (e) => toast(errorMessage(e), "danger"),
  });
  const remove = useMutation({
    mutationFn: (id: string) => deleteAudience(organization.id, id),
    onSuccess: () => {
      setDeleting(null);
      toast("Audience removed.");
      return invalidate();
    },
    onError: (e) => toast(errorMessage(e), "danger"),
  });

  if (audiences.isPending) return <PageLoading />;
  if (audiences.isError) return <Alert tone="danger">{errorMessage(audiences.error)}</Alert>;

  const items = audiences.data.results;
  const preset = reference.data?.industries.find((i) => i.key === profile.data?.industry);
  const suggestions = (preset?.example_audiences ?? []).filter(
    (s) => !items.some((a) => a.name === s),
  );

  return (
    <div className="flex flex-col gap-4">
      {items.length === 0 ? (
        <EmptyState
          title="No audiences yet"
          description="Describe who you want to reach. Content and plans are tailored to these groups."
        />
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2">
          {items.map((a) => (
            <li key={a.id} className="flex flex-col gap-2 rounded-lg border border-border p-4">
              <div className="flex items-start justify-between gap-2">
                <p className="font-medium">{a.name}</p>
                {a.is_primary && <Badge tone="info">Primary</Badge>}
              </div>
              {a.description && <p className="text-sm text-muted">{a.description}</p>}
              {(a.age_range || a.locations) && (
                <p className="text-xs text-muted">
                  {[a.age_range, a.locations].filter(Boolean).join(" · ")}
                </p>
              )}
              {canEdit && (
                <div className="mt-auto flex gap-2 pt-1">
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => {
                      setEditing(a);
                      setDialogOpen(true);
                    }}
                  >
                    Edit
                  </Button>
                  <Button variant="ghost" size="sm" onClick={() => setDeleting(a)}>
                    Remove
                  </Button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}

      {canEdit && (
        <div className="flex flex-wrap items-center gap-2">
          <Button
            onClick={() => {
              setEditing(null);
              setDialogOpen(true);
            }}
          >
            + Add audience
          </Button>
          {suggestions.map((s) => (
            <Button
              key={s}
              variant="secondary"
              size="sm"
              disabled={quickAdd.isPending}
              onClick={() => quickAdd.mutate(s)}
            >
              + {s}
            </Button>
          ))}
        </div>
      )}
      {suggestions.length > 0 && canEdit && (
        <p className="text-xs text-muted">
          Suggestions are common for your industry. Edit them to describe your actual customers.
        </p>
      )}

      <AudienceDialog audience={editing} open={dialogOpen} onClose={() => setDialogOpen(false)} />
      <ConfirmDialog
        open={deleting !== null}
        onCancel={() => setDeleting(null)}
        onConfirm={() => deleting && remove.mutate(deleting.id)}
        pending={remove.isPending}
        title="Remove audience?"
        description={`"${deleting?.name}" will no longer be used for plans and content.`}
        confirmLabel="Remove"
      />
    </div>
  );
}
