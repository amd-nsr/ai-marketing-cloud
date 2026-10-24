import { useMutation, useQueryClient } from "@tanstack/react-query";

import { useToast } from "@/components/ui/toast";
import { useOrg } from "@/hooks/use-org";
import { type PolicyChanges, updatePolicy } from "@/lib/api/automation";
import { errorMessage } from "@/lib/api/errors";

export function usePolicyMutation() {
  const { organization } = useOrg();
  const queryClient = useQueryClient();
  const toast = useToast();
  return useMutation({
    mutationFn: (changes: PolicyChanges) => updatePolicy(organization.id, changes),
    onSuccess: (policy) => {
      queryClient.setQueryData(["orgs", organization.id, "automation", "policy"], policy);
      void queryClient.invalidateQueries({
        queryKey: ["orgs", organization.id, "automation", "actions"],
      });
      toast("Automation settings saved. Pending work was re-checked against them.");
    },
    onError: (e) => toast(errorMessage(e), "danger"),
  });
}
