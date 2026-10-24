import { Suspense } from "react";

import { PageLoading } from "@/components/ui/spinner";
import { MetaConnectionPage } from "@/features/social/meta-connection-page";

export const metadata = { title: "Meta connection" };

export default function Page() {
  return (
    <Suspense fallback={<PageLoading />}>
      <MetaConnectionPage />
    </Suspense>
  );
}
