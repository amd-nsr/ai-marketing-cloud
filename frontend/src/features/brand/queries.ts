"use client";

import { useQuery } from "@tanstack/react-query";

import { useOrg } from "@/hooks/use-org";
import {
  getBrandGuideline,
  getBusinessProfile,
  getOnboarding,
  getReferenceData,
  listAudiences,
  listBrandAssets,
} from "@/lib/api/brand";

export const brandKeys = {
  profile: (orgId: string) => ["orgs", orgId, "business-profile"] as const,
  guideline: (orgId: string) => ["orgs", orgId, "brand-guideline"] as const,
  audiences: (orgId: string) => ["orgs", orgId, "audiences"] as const,
  assets: (orgId: string) => ["orgs", orgId, "brand-assets"] as const,
  onboarding: (orgId: string) => ["orgs", orgId, "onboarding"] as const,
  context: (orgId: string) => ["orgs", orgId, "business-context"] as const,
};

export function useReferenceData() {
  return useQuery({ queryKey: ["reference-data"], queryFn: getReferenceData, staleTime: Infinity });
}

export function useBusinessProfile() {
  const { organization } = useOrg();
  return useQuery({
    queryKey: brandKeys.profile(organization.id),
    queryFn: () => getBusinessProfile(organization.id),
  });
}

export function useBrandGuideline() {
  const { organization } = useOrg();
  return useQuery({
    queryKey: brandKeys.guideline(organization.id),
    queryFn: () => getBrandGuideline(organization.id),
  });
}

export function useAudiences() {
  const { organization } = useOrg();
  return useQuery({
    queryKey: brandKeys.audiences(organization.id),
    queryFn: () => listAudiences(organization.id),
  });
}

export function useBrandAssets() {
  const { organization } = useOrg();
  return useQuery({
    queryKey: brandKeys.assets(organization.id),
    queryFn: () => listBrandAssets(organization.id),
  });
}

export function useOnboarding() {
  const { organization } = useOrg();
  return useQuery({
    queryKey: brandKeys.onboarding(organization.id),
    queryFn: () => getOnboarding(organization.id),
  });
}

/** Keys to refresh after any brand edit (onboarding progress and AI context depend on all of it). */
export const brandDependents = (orgId: string) => [
  brandKeys.onboarding(orgId),
  brandKeys.context(orgId),
];
