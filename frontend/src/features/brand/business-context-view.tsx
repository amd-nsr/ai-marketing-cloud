"use client";

import { useQuery } from "@tanstack/react-query";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { PageLoading } from "@/components/ui/spinner";
import { useOrg } from "@/hooks/use-org";
import { getBusinessContext } from "@/lib/api/brand";
import { errorMessage } from "@/lib/api/errors";

import { brandKeys } from "./queries";

const SECTION_LABELS: Record<string, string> = {
  business: "Business",
  goals: "Goals",
  platforms: "Platforms",
  audiences: "Audiences",
  brand_voice: "Brand voice",
  restrictions: "Restrictions",
  industry_guidance: "Industry guidance",
};

function renderValue(value: unknown): React.ReactNode {
  if (value === null || value === undefined || value === "")
    return <span className="text-muted">Not provided</span>;
  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="text-muted">None</span>;
    return (
      <ul className="list-disc pl-5">
        {value.map((v, i) => (
          <li key={i}>{typeof v === "object" ? renderValue(v) : String(v)}</li>
        ))}
      </ul>
    );
  }
  if (typeof value === "object") {
    return (
      <dl className="grid gap-x-4 gap-y-1 sm:grid-cols-[10rem_1fr]">
        {Object.entries(value as Record<string, unknown>)
          .filter(([k]) => k !== "source" && k !== "note")
          .map(([k, v]) => (
            <div key={k} className="contents">
              <dt className="text-muted">{k.replaceAll("_", " ")}</dt>
              <dd>{renderValue(v)}</dd>
            </div>
          ))}
      </dl>
    );
  }
  return String(value);
}

/** Shows exactly what AI workflows receive, with the source of each section. */
export function BusinessContextView() {
  const { organization } = useOrg();
  const context = useQuery({
    queryKey: brandKeys.context(organization.id),
    queryFn: () => getBusinessContext(organization.id),
  });
  if (context.isPending) return <PageLoading />;
  if (context.isError) return <Alert tone="danger">{errorMessage(context.error)}</Alert>;

  return (
    <div className="flex flex-col gap-4">
      <Alert tone="info">
        This is the complete business context the AI receives when planning or writing for you.
        Sections marked &ldquo;You provided&rdquo; are treated as facts; industry guidance is
        generic and never presented as a fact about your business.
      </Alert>
      {Object.entries(context.data).map(([key, section]) => {
        if (!section || typeof section !== "object") return null;
        const source = (section as { source?: string }).source;
        return (
          <section key={key} className="rounded-lg border border-border p-4">
            <div className="mb-2 flex items-center justify-between gap-2">
              <h3 className="text-sm font-semibold">{SECTION_LABELS[key] ?? key}</h3>
              {source === "user" && <Badge tone="success">You provided</Badge>}
              {source === "industry_preset" && (
                <Badge tone="warning">Generic industry guidance</Badge>
              )}
            </div>
            <div className="text-sm">
              {renderValue("items" in section ? (section as { items: unknown }).items : section)}
            </div>
          </section>
        );
      })}
    </div>
  );
}
