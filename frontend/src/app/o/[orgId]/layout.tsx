import { Suspense } from "react";

import { PageLoading } from "@/components/ui/spinner";
import { OrgGate } from "@/features/org/org-gate";

// OrgGate reads the dynamic [orgId] param, which is unknown at prerender time, so it
// must sit inside a Suspense boundary (Cache Components).
export default function OrgLayout({ children }: LayoutProps<"/o/[orgId]">) {
  return (
    <Suspense fallback={<PageLoading />}>
      <OrgGate>{children}</OrgGate>
    </Suspense>
  );
}
