import { Suspense } from "react";

import { PageLoading } from "@/components/ui/spinner";
import { CampaignPage } from "@/features/ads/campaign-page";

export const metadata = { title: "Ad campaign" };

export default function Page() {
  return (
    <Suspense fallback={<PageLoading />}>
      <CampaignPage />
    </Suspense>
  );
}
