"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";

import { useOrg } from "@/hooks/use-org";
import { getContent, listAssets, listItemApprovals, listVersions } from "@/lib/api/content";

export const contentKeys = {
  all: (orgId: string) => ["orgs", orgId, "content"] as const,
  item: (orgId: string, id: string) => ["orgs", orgId, "content", id] as const,
  versions: (orgId: string, id: string) => ["orgs", orgId, "content", id, "versions"] as const,
  assets: (orgId: string, id: string) => ["orgs", orgId, "content", id, "assets"] as const,
  approvals: (orgId: string, id: string) => ["orgs", orgId, "content", id, "approvals"] as const,
};

export function useContentItem(id: string) {
  const { organization } = useOrg();
  return useQuery({
    queryKey: contentKeys.item(organization.id, id),
    queryFn: () => getContent(organization.id, id),
  });
}

export function useVersions(id: string) {
  const { organization } = useOrg();
  return useQuery({
    queryKey: contentKeys.versions(organization.id, id),
    queryFn: () => listVersions(organization.id, id),
  });
}

export function useAssets(id: string) {
  const { organization } = useOrg();
  return useQuery({
    queryKey: contentKeys.assets(organization.id, id),
    queryFn: () => listAssets(organization.id, id),
  });
}

export function useItemApprovals(id: string) {
  const { organization } = useOrg();
  return useQuery({
    queryKey: contentKeys.approvals(organization.id, id),
    queryFn: () => listItemApprovals(organization.id, id),
  });
}

/** Refresh everything about one item (status, versions, approvals) plus lists. */
export function useRefreshItem() {
  const { organization } = useOrg();
  const queryClient = useQueryClient();
  return () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: contentKeys.all(organization.id) }),
      queryClient.invalidateQueries({ queryKey: ["orgs", organization.id, "approvals"] }),
      queryClient.invalidateQueries({ queryKey: ["orgs", organization.id, "publishing"] }),
    ]);
}
