import { Suspense } from "react";

import { PageLoading } from "@/components/ui/spinner";
import { DataDeletionStatus } from "@/features/social/data-deletion-status";

export const metadata = { title: "Data deletion status" };

/** Public page Meta links to after a data deletion request (no sign-in required). */
export default function Page() {
  return (
    <main className="mx-auto w-full max-w-xl px-4 py-12">
      <Suspense fallback={<PageLoading />}>
        <DataDeletionStatus />
      </Suspense>
    </main>
  );
}
