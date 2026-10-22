"use client";

import { createContext, type ReactNode, useContext, useEffect } from "react";

import { rememberOrg } from "@/features/org/home-redirect";

import type { Membership, Organization } from "@/lib/api/auth";

interface OrgContextValue {
  organization: Organization;
  membership: Membership;
  /** UI hint only. The server enforces every permission independently. */
  can: (permission: string) => boolean;
}

const OrgContext = createContext<OrgContextValue | null>(null);

export function OrgProvider({
  membership,
  children,
}: {
  membership: Membership;
  children: ReactNode;
}) {
  useEffect(() => rememberOrg(membership.organization.id), [membership.organization.id]);
  const value: OrgContextValue = {
    organization: membership.organization,
    membership,
    can: (permission) => membership.permissions.includes(permission),
  };
  return <OrgContext.Provider value={value}>{children}</OrgContext.Provider>;
}

export function useOrg(): OrgContextValue {
  const ctx = useContext(OrgContext);
  if (!ctx) throw new Error("useOrg must be used inside an organization route.");
  return ctx;
}
