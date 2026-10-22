"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input, Select } from "@/components/ui/input";
import { PageHeader } from "@/components/ui/page-header";
import { PageLoading } from "@/components/ui/spinner";
import { useToast } from "@/components/ui/toast";
import { ME_QUERY_KEY } from "@/hooks/use-me";
import { useOrg } from "@/hooks/use-org";
import type { Role } from "@/lib/api/auth";
import { errorMessage } from "@/lib/api/errors";
import {
  createInvitation,
  listInvitations,
  listMembers,
  type Member,
  removeMember,
  revokeInvitation,
  updateMemberRole,
  updateOrganization,
} from "@/lib/api/organizations";
import { ROLE_DESCRIPTIONS, ROLE_LABELS } from "@/lib/auth/roles";
import { formatDate } from "@/lib/format";
import { applyServerErrors } from "@/lib/validation/forms";
import { zodResolver } from "@/lib/validation/zod-resolver";

const ROLES = Object.keys(ROLE_LABELS) as Role[];

function OrgNameCard() {
  const { organization, can } = useOrg();
  const queryClient = useQueryClient();
  const toast = useToast();
  const schema = z.object({
    name: z.string().trim().min(2, "Enter at least 2 characters.").max(120),
  });
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    values: { name: organization.name },
  });
  const onSubmit = form.handleSubmit(async (values) => {
    try {
      await updateOrganization(organization.id, values);
      await queryClient.invalidateQueries({ queryKey: ME_QUERY_KEY });
      toast("Organization updated.");
    } catch (error) {
      const message = applyServerErrors(error, form.setError, ["name"]);
      if (message) toast(message, "danger");
    }
  });
  return (
    <Card>
      <CardHeader
        title="Organization"
        description="The name your team sees across the workspace."
      />
      <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4 sm:flex-row sm:items-end">
        <Field label="Name" error={form.formState.errors.name?.message} className="flex-1">
          {(p) => <Input {...p} {...form.register("name")} disabled={!can("org.manage")} />}
        </Field>
        {can("org.manage") && (
          <Button type="submit" disabled={form.formState.isSubmitting || !form.formState.isDirty}>
            Save
          </Button>
        )}
      </form>
    </Card>
  );
}

function MembersCard() {
  const { organization, membership, can } = useOrg();
  const queryClient = useQueryClient();
  const toast = useToast();
  const [removing, setRemoving] = useState<Member | null>(null);
  const key = ["orgs", organization.id, "members"];
  const members = useQuery({ queryKey: key, queryFn: () => listMembers(organization.id) });
  const manage = can("members.manage");
  const isOwner = membership.role === "owner";

  const roleMutation = useMutation({
    mutationFn: ({ id, role }: { id: string; role: Role }) =>
      updateMemberRole(organization.id, id, role),
    onSuccess: () => {
      toast("Role updated.");
      return Promise.all([
        queryClient.invalidateQueries({ queryKey: key }),
        queryClient.invalidateQueries({ queryKey: ME_QUERY_KEY }),
      ]);
    },
    onError: (e) => toast(errorMessage(e), "danger"),
  });
  const removeMutation = useMutation({
    mutationFn: (id: string) => removeMember(organization.id, id),
    onSuccess: () => {
      toast("Member removed.");
      setRemoving(null);
      return queryClient.invalidateQueries({ queryKey: key });
    },
    onError: (e) => {
      toast(errorMessage(e), "danger");
      setRemoving(null);
    },
  });

  return (
    <Card>
      <CardHeader title="Members" description="People with access to this organization." />
      {members.isPending && <PageLoading />}
      {members.isError && <Alert tone="danger">{errorMessage(members.error)}</Alert>}
      {members.data && (
        <ul className="divide-y divide-border">
          {members.data.results.map((m) => {
            const self = m.id === membership.id;
            const canEdit = manage && (isOwner || m.role !== "owner");
            return (
              <li key={m.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">
                    {m.full_name || m.email} {self && <Badge>You</Badge>}
                  </p>
                  <p className="truncate text-xs text-muted">{m.email}</p>
                </div>
                <div className="flex items-center gap-2">
                  {canEdit ? (
                    <Select
                      aria-label={`Role for ${m.email}`}
                      value={m.role}
                      className="w-32"
                      disabled={roleMutation.isPending}
                      onChange={(e) =>
                        roleMutation.mutate({ id: m.id, role: e.target.value as Role })
                      }
                    >
                      {ROLES.filter((r) => isOwner || r !== "owner").map((r) => (
                        <option key={r} value={r}>
                          {ROLE_LABELS[r]}
                        </option>
                      ))}
                    </Select>
                  ) : (
                    <Badge>{ROLE_LABELS[m.role]}</Badge>
                  )}
                  {(canEdit || self) && (
                    <Button variant="ghost" size="sm" onClick={() => setRemoving(m)}>
                      {self ? "Leave" : "Remove"}
                    </Button>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
      <ConfirmDialog
        open={removing !== null}
        onCancel={() => setRemoving(null)}
        onConfirm={() => removing && removeMutation.mutate(removing.id)}
        pending={removeMutation.isPending}
        title={removing?.id === membership.id ? "Leave organization?" : "Remove member?"}
        description={
          removing?.id === membership.id
            ? "You will lose access to this organization immediately."
            : `${removing?.email} will lose access to ${organization.name} immediately.`
        }
        confirmLabel={removing?.id === membership.id ? "Leave" : "Remove"}
      />
    </Card>
  );
}

function InvitationsCard() {
  const { organization, membership } = useOrg();
  const queryClient = useQueryClient();
  const toast = useToast();
  const key = ["orgs", organization.id, "invitations"];
  const invitations = useQuery({ queryKey: key, queryFn: () => listInvitations(organization.id) });
  const schema = z.object({
    email: z.string().trim().email("Enter a valid email address."),
    role: z.enum(["owner", "admin", "editor", "analyst", "viewer"]),
  });
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: { email: "", role: "editor" },
  });
  const role = useWatch({ control: form.control, name: "role" });

  const onSubmit = form.handleSubmit(async (values) => {
    try {
      await createInvitation(organization.id, values);
      form.reset({ email: "", role: values.role });
      toast(`Invitation sent to ${values.email}.`);
      await queryClient.invalidateQueries({ queryKey: key });
    } catch (error) {
      const message = applyServerErrors(error, form.setError, ["email", "role"]);
      if (message) toast(message, "danger");
    }
  });

  const revoke = useMutation({
    mutationFn: (id: string) => revokeInvitation(organization.id, id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: key }),
    onError: (e) => toast(errorMessage(e), "danger"),
  });

  return (
    <Card>
      <CardHeader title="Invite people" description="Invitations expire after 7 days." />
      <form
        onSubmit={onSubmit}
        noValidate
        className="grid gap-4 sm:grid-cols-[1fr_10rem_auto] sm:items-start"
      >
        <Field label="Email" error={form.formState.errors.email?.message}>
          {(p) => <Input type="email" {...p} {...form.register("email")} />}
        </Field>
        <Field label="Role">
          {(p) => (
            <Select {...p} {...form.register("role")}>
              {ROLES.filter((r) => membership.role === "owner" || r !== "owner").map((r) => (
                <option key={r} value={r}>
                  {ROLE_LABELS[r]}
                </option>
              ))}
            </Select>
          )}
        </Field>
        <Button type="submit" className="sm:mt-6" disabled={form.formState.isSubmitting}>
          Send invite
        </Button>
      </form>
      <p className="mt-2 text-xs text-muted">{ROLE_DESCRIPTIONS[role]}</p>

      {invitations.data && invitations.data.results.length > 0 && (
        <div className="mt-6">
          <h3 className="mb-2 text-sm font-medium">Pending</h3>
          <ul className="divide-y divide-border">
            {invitations.data.results.map((inv) => (
              <li key={inv.id} className="flex flex-wrap items-center justify-between gap-3 py-2">
                <div className="min-w-0">
                  <p className="truncate text-sm">{inv.email}</p>
                  <p className="text-xs text-muted">
                    {ROLE_LABELS[inv.role]} · expires {formatDate(inv.expires_at)}
                  </p>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => revoke.mutate(inv.id)}
                  disabled={revoke.isPending}
                >
                  Revoke
                </Button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
}

export function OrganizationSettings() {
  const { can } = useOrg();
  return (
    <>
      <PageHeader title="Settings" description="Manage your organization and team." />
      <div className="flex flex-col gap-6">
        <OrgNameCard />
        {can("members.view") && <MembersCard />}
        {can("members.manage") && <InvitationsCard />}
      </div>
    </>
  );
}
