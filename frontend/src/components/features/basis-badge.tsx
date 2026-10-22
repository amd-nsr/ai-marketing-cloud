import { Badge } from "@/components/ui/badge";
import type { Basis } from "@/lib/api/marketing";

const BASIS: Record<
  Basis,
  { label: string; tone: "success" | "warning" | "neutral"; title: string }
> = {
  user_provided: {
    label: "You provided",
    tone: "success",
    title: "Based on information you gave us.",
  },
  industry_guidance: {
    label: "Industry guidance",
    tone: "neutral",
    title: "Generic industry guidance, not a fact about your business.",
  },
  ai_assumption: {
    label: "AI assumption",
    tone: "warning",
    title: "Assumed by the AI. Check it before relying on it.",
  },
};

export function BasisBadge({ basis }: { basis: Basis }) {
  const b = BASIS[basis];
  return (
    <Badge tone={b.tone} title={b.title}>
      {b.label}
    </Badge>
  );
}
