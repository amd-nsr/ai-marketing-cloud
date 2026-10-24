"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button, buttonClasses } from "@/components/ui/button";
import { CheckboxGroup } from "@/components/ui/checkbox-group";
import { ConfirmDialog, Dialog } from "@/components/ui/dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { Field } from "@/components/ui/field";
import { Input, Select, Textarea } from "@/components/ui/input";
import { PageHeader } from "@/components/ui/page-header";
import { PageLoading } from "@/components/ui/spinner";
import { TagInput } from "@/components/ui/tag-input";
import { useToast } from "@/components/ui/toast";
import { useOrg } from "@/hooks/use-org";
import {
  type Campaign,
  createCampaign,
  deleteCampaign,
  listCampaigns,
  updateCampaign,
} from "@/lib/api/content";
import { errorMessage } from "@/lib/api/errors";
import { formatDate } from "@/lib/format";
import { applyServerErrors } from "@/lib/validation/forms";
import { zodResolver } from "@/lib/validation/zod-resolver";
import { PLATFORM_LABEL, SOCIAL_PLATFORMS } from "@/features/content/labels";

const STATUS_TONE = {
  planned: "info",
  active: "success",
  completed: "neutral",
  archived: "neutral",
} as const;

const schema = z
  .object({
    name: z.string().trim().min(2, "Name the campaign.").max(160),
    objective: z.string().trim().max(300),
    description: z.string().trim().max(4000),
    status: z.enum(["planned", "active", "completed", "archived"]),
    start_date: z.string(),
    end_date: z.string(),
    platforms: z.array(z.enum(["instagram", "facebook", "tiktok"])),
    key_messages: z.array(z.string()).max(10),
  })
  .refine((v) => !v.start_date || !v.end_date || v.end_date >= v.start_date, {
    path: ["end_date"],
    message: "End date must be on or after the start date.",
  });
type Values = z.infer<typeof schema>;

function CampaignDialog({ campaign, onClose }: { campaign: Campaign | null; onClose: () => void }) {
  const { organization } = useOrg();
  const queryClient = useQueryClient();
  const toast = useToast();
  const [error, setError] = useState<string | null>(null);
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: campaign?.name ?? "",
      objective: campaign?.objective ?? "",
      description: campaign?.description ?? "",
      status: campaign?.status ?? "planned",
      start_date: campaign?.start_date ?? "",
      end_date: campaign?.end_date ?? "",
      platforms: campaign?.platforms ?? [],
      key_messages: campaign?.key_messages ?? [],
    },
  });
  const { errors } = form.formState;

  const submit = form.handleSubmit(async (values) => {
    setError(null);
    const body = {
      ...values,
      start_date: values.start_date || null,
      end_date: values.end_date || null,
    };
    try {
      if (campaign) await updateCampaign(organization.id, campaign.id, body);
      else await createCampaign(organization.id, body);
      await queryClient.invalidateQueries({ queryKey: ["orgs", organization.id, "campaigns"] });
      toast(campaign ? "Campaign updated." : "Campaign created.");
      onClose();
    } catch (e) {
      setError(applyServerErrors(e, form.setError, Object.keys(values)));
    }
  });

  return (
    <Dialog
      open
      onClose={onClose}
      title={campaign ? "Edit campaign" : "New campaign"}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={form.formState.isSubmitting}>
            Save campaign
          </Button>
        </>
      }
    >
      <form onSubmit={submit} noValidate className="flex flex-col gap-4">
        {error && <Alert tone="danger">{error}</Alert>}
        <Field label="Name" error={errors.name?.message}>
          {(p) => <Input {...p} {...form.register("name")} />}
        </Field>
        <Field label="Objective" optional>
          {(p) => (
            <Input
              placeholder="e.g. Fill weekday lunch tables"
              {...p}
              {...form.register("objective")}
            />
          )}
        </Field>
        <Field label="Description" optional>
          {(p) => <Textarea rows={3} {...p} {...form.register("description")} />}
        </Field>
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Status">
            {(p) => (
              <Select {...p} {...form.register("status")}>
                <option value="planned">Planned</option>
                <option value="active">Active</option>
                <option value="completed">Completed</option>
                <option value="archived">Archived</option>
              </Select>
            )}
          </Field>
          <Field label="Starts" optional>
            {(p) => <Input type="date" {...p} {...form.register("start_date")} />}
          </Field>
          <Field label="Ends" optional error={errors.end_date?.message}>
            {(p) => <Input type="date" {...p} {...form.register("end_date")} />}
          </Field>
        </div>
        <Controller
          control={form.control}
          name="platforms"
          render={({ field }) => (
            <CheckboxGroup
              legend="Platforms"
              columns={3}
              options={SOCIAL_PLATFORMS.map((value) => ({ value, label: PLATFORM_LABEL[value] }))}
              value={field.value}
              onChange={field.onChange}
            />
          )}
        />
        <Controller
          control={form.control}
          name="key_messages"
          render={({ field }) => (
            <Field
              label="Key messages"
              optional
              hint="Press Enter after each. Used when generating content."
            >
              {(p) => (
                <TagInput
                  {...p}
                  value={field.value}
                  onChange={field.onChange}
                  maxItems={10}
                  maxLength={300}
                />
              )}
            </Field>
          )}
        />
      </form>
    </Dialog>
  );
}

export function CampaignsPage() {
  const { organization, can } = useOrg();
  const queryClient = useQueryClient();
  const toast = useToast();
  const [editing, setEditing] = useState<Campaign | null | "new">(null);
  const [deleting, setDeleting] = useState<Campaign | null>(null);
  const campaigns = useQuery({
    queryKey: ["orgs", organization.id, "campaigns"],
    queryFn: () => listCampaigns(organization.id),
  });
  const remove = useMutation({
    mutationFn: (id: string) => deleteCampaign(organization.id, id),
    onSuccess: () => {
      setDeleting(null);
      toast("Campaign deleted.");
      return queryClient.invalidateQueries({ queryKey: ["orgs", organization.id, "campaigns"] });
    },
    onError: (e) => {
      setDeleting(null);
      toast(errorMessage(e), "danger");
    },
  });
  const canEdit = can("campaign.edit");

  return (
    <>
      <PageHeader
        title="Campaigns"
        description="Group content around a goal and a time window."
        actions={canEdit && <Button onClick={() => setEditing("new")}>New campaign</Button>}
      />
      {campaigns.isPending && <PageLoading />}
      {campaigns.isError && <Alert tone="danger">{errorMessage(campaigns.error)}</Alert>}
      {campaigns.data?.count === 0 && (
        <EmptyState
          title="No campaigns yet"
          description="Create one from scratch, or use a campaign concept from your marketing plan."
          action={canEdit && <Button onClick={() => setEditing("new")}>New campaign</Button>}
        />
      )}
      {campaigns.data && campaigns.data.count > 0 && (
        <ul className="grid gap-3 md:grid-cols-2">
          {campaigns.data.results.map((c) => (
            <li
              key={c.id}
              className="flex flex-col gap-2 rounded-lg border border-border bg-surface p-4"
            >
              <div className="flex flex-wrap items-center gap-2">
                <p className="font-medium">{c.name}</p>
                <Badge tone={STATUS_TONE[c.status]}>{c.status}</Badge>
              </div>
              {c.objective && <p className="text-sm">{c.objective}</p>}
              <p className="text-xs text-muted">
                {c.start_date || c.end_date
                  ? `${formatDate(c.start_date)} – ${formatDate(c.end_date)}`
                  : "No dates"}{" "}
                · {c.platforms.map((p) => PLATFORM_LABEL[p]).join(", ") || "Any platform"}
              </p>
              <div className="mt-auto flex flex-wrap gap-2 pt-2">
                <Link
                  href={`/o/${organization.id}/content?campaign=${c.id}`}
                  className={buttonClasses("secondary", "sm")}
                >
                  {c.content_count} content item{c.content_count === 1 ? "" : "s"}
                </Link>
                {canEdit && (
                  <>
                    <Button size="sm" variant="ghost" onClick={() => setEditing(c)}>
                      Edit
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => setDeleting(c)}>
                      Delete
                    </Button>
                  </>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
      {editing !== null && (
        <CampaignDialog
          campaign={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
        />
      )}
      <ConfirmDialog
        open={deleting !== null}
        onCancel={() => setDeleting(null)}
        onConfirm={() => deleting && remove.mutate(deleting.id)}
        pending={remove.isPending}
        title="Delete campaign?"
        description="Only campaigns without active content can be deleted. Archiving keeps the history."
        confirmLabel="Delete"
      />
    </>
  );
}
