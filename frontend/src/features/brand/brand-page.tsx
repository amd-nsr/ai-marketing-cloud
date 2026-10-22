"use client";

import { useState } from "react";

import { Card } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { Tabs } from "@/components/ui/tabs";

import { AssetsManager } from "./assets-manager";
import { AudiencesEditor } from "./audiences-editor";
import { BrandVoiceForm } from "./brand-voice-form";
import { BusinessBasicsForm } from "./business-basics-form";
import { BusinessContextView } from "./business-context-view";
import { GoalsPlatformsForm } from "./goals-platforms-form";

type Tab = "business" | "audiences" | "goals" | "voice" | "assets" | "context";

const TABS: { value: Tab; label: string }[] = [
  { value: "business", label: "Business" },
  { value: "audiences", label: "Audiences" },
  { value: "goals", label: "Goals & platforms" },
  { value: "voice", label: "Brand voice" },
  { value: "assets", label: "Assets" },
  { value: "context", label: "What the AI sees" },
];

export function BrandPage() {
  const [tab, setTab] = useState<Tab>("business");
  return (
    <>
      <PageHeader
        title="Business & brand"
        description="The facts and guidelines every plan and post is built on."
      />
      <Tabs label="Brand sections" value={tab} onChange={setTab} items={TABS} />
      <Card className="mt-4">
        {tab === "business" && <BusinessBasicsForm />}
        {tab === "audiences" && <AudiencesEditor />}
        {tab === "goals" && <GoalsPlatformsForm />}
        {tab === "voice" && <BrandVoiceForm />}
        {tab === "assets" && <AssetsManager />}
        {tab === "context" && <BusinessContextView />}
      </Card>
    </>
  );
}
