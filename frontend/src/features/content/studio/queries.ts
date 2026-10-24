"use client";

import { useQuery } from "@tanstack/react-query";

import { useBrandGuideline } from "@/features/brand/queries";
import { useOrg } from "@/hooks/use-org";
import { getStudioCapabilities, listLibrary, listTemplates } from "@/lib/api/content";

export const studioKeys = {
  capabilities: (orgId: string) => ["orgs", orgId, "studio-capabilities"] as const,
  library: (orgId: string) => ["orgs", orgId, "library"] as const,
  libraryList: (orgId: string, filters: object) => ["orgs", orgId, "library", filters] as const,
  templates: (orgId: string, kind?: string) => ["orgs", orgId, "templates", kind ?? ""] as const,
};

export function useStudioCapabilities() {
  const { organization } = useOrg();
  return useQuery({
    queryKey: studioKeys.capabilities(organization.id),
    queryFn: () => getStudioCapabilities(organization.id),
    staleTime: 5 * 60_000,
  });
}

export function useLibrary(filters: { kind?: string; q?: string; tag?: string } = {}) {
  const { organization } = useOrg();
  return useQuery({
    queryKey: studioKeys.libraryList(organization.id, filters),
    queryFn: () => listLibrary(organization.id, filters),
  });
}

export function useTemplates(kind?: string) {
  const { organization } = useOrg();
  return useQuery({
    queryKey: studioKeys.templates(organization.id, kind),
    queryFn: () => listTemplates(organization.id, kind),
  });
}

export interface BrandPalette {
  colors: string[];
  fonts: string[];
}

/** Web-safe fallbacks offered next to the brand's own fonts. */
export const BASE_FONTS = [
  "Inter",
  "Arial",
  "Helvetica",
  "Georgia",
  "Times New Roman",
  "Verdana",
  "Trebuchet MS",
  "Courier New",
];

export function useBrandPalette(): BrandPalette {
  const guideline = useBrandGuideline();
  const colors = (guideline.data?.colors ?? []).filter((c) => /^#[0-9a-fA-F]{6}$/.test(c));
  const fonts = guideline.data?.fonts ?? [];
  return { colors, fonts };
}
