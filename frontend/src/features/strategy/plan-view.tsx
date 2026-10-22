"use client";

import type { ReactNode } from "react";

import { BasisBadge } from "@/components/features/basis-badge";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import type { Plan } from "@/lib/api/marketing";

const PLATFORM_LABEL = { instagram: "Instagram", facebook: "Facebook", tiktok: "TikTok" } as const;
const FORMAT_LABEL = {
  post: "Post",
  carousel: "Carousel",
  reel: "Reel",
  story: "Story",
  short_video: "Short video",
} as const;

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-3">
      <h3 className="text-sm font-semibold tracking-wide text-muted uppercase">{title}</h3>
      {children}
    </section>
  );
}

export function PlanView({ plan }: { plan: Plan }) {
  const c = plan.content;
  const weeks = Array.from(new Set(c.content_calendar.map((e) => e.week))).sort((a, b) => a - b);
  return (
    <div className="flex flex-col gap-8">
      {plan.quality_warnings.length > 0 && (
        <Alert tone="warning" title="Review before using">
          <ul className="list-disc pl-5">
            {plan.quality_warnings.map((w, i) => (
              <li key={i}>
                {w.message}
                {w.excerpt && <span className="text-muted"> — “{w.excerpt}”</span>}
              </li>
            ))}
          </ul>
        </Alert>
      )}

      <p className="max-w-prose whitespace-pre-line">{c.summary}</p>

      <Section title="Objectives">
        <div className="grid gap-3 md:grid-cols-2">
          {c.objectives.map((o, i) => (
            <div key={i} className="rounded-lg border border-border p-4">
              <p className="font-medium">{o.title}</p>
              <p className="mt-1 text-sm text-muted">{o.description}</p>
              <dl className="mt-3 grid grid-cols-[6rem_1fr] gap-y-1 text-sm">
                <dt className="text-muted">Metric</dt>
                <dd>{o.metric}</dd>
                <dt className="text-muted">Target</dt>
                <dd>{o.target}</dd>
                <dt className="text-muted">Timeframe</dt>
                <dd>{o.timeframe}</dd>
              </dl>
            </div>
          ))}
        </div>
        <p className="text-xs text-muted">Targets are hypotheses to test, not predicted results.</p>
      </Section>

      <Section title="Channel allocation">
        <ul className="flex flex-col gap-2">
          {c.channel_allocation.map((a) => (
            <li key={a.platform} className="grid gap-1 sm:grid-cols-[8rem_1fr]">
              <span className="text-sm font-medium">
                {PLATFORM_LABEL[a.platform]} · {a.share_percent}%
              </span>
              <div>
                <div className="h-2 overflow-hidden rounded-full bg-neutral-soft">
                  <div className="h-full bg-primary" style={{ width: `${a.share_percent}%` }} />
                </div>
                <p className="mt-1 text-xs text-muted">{a.rationale}</p>
              </div>
            </li>
          ))}
        </ul>
      </Section>

      <Section title="Content themes">
        <div className="grid gap-3 md:grid-cols-2">
          {c.content_themes.map((t, i) => (
            <div key={i} className="rounded-lg border border-border p-4">
              <p className="font-medium">{t.name}</p>
              <p className="mt-1 text-sm text-muted">{t.description}</p>
              {t.example_ideas.length > 0 && (
                <ul className="mt-2 list-disc pl-5 text-sm">
                  {t.example_ideas.map((idea, j) => (
                    <li key={j}>{idea}</li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </div>
      </Section>

      <Section title="Campaign concepts">
        <div className="flex flex-col gap-3">
          {c.campaign_concepts.map((cc, i) => (
            <div key={i} className="rounded-lg border border-border p-4">
              <div className="flex flex-wrap items-center gap-2">
                <p className="font-medium">{cc.name}</p>
                <Badge>{cc.duration_weeks} weeks</Badge>
                {cc.platforms.map((p) => (
                  <Badge key={p} tone="info">
                    {PLATFORM_LABEL[p]}
                  </Badge>
                ))}
              </div>
              <p className="mt-1 text-sm">{cc.description}</p>
              <p className="mt-1 text-xs text-muted">Objective: {cc.objective}</p>
              {cc.key_messages.length > 0 && (
                <ul className="mt-2 list-disc pl-5 text-sm">
                  {cc.key_messages.map((m, j) => (
                    <li key={j}>{m}</li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </div>
      </Section>

      <Section title={`Content calendar (${plan.horizon_weeks} weeks)`}>
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full min-w-[36rem] text-sm">
            <thead className="bg-neutral-soft text-left text-xs text-muted">
              <tr>
                <th className="px-3 py-2 font-medium">Week</th>
                <th className="px-3 py-2 font-medium">Day</th>
                <th className="px-3 py-2 font-medium">Platform</th>
                <th className="px-3 py-2 font-medium">Format</th>
                <th className="px-3 py-2 font-medium">Idea</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {weeks.flatMap((w) =>
                c.content_calendar
                  .filter((e) => e.week === w)
                  .map((e, i) => (
                    <tr key={`${w}-${i}`}>
                      <td className="px-3 py-2 whitespace-nowrap">{i === 0 ? `Week ${w}` : ""}</td>
                      <td className="px-3 py-2">{e.day}</td>
                      <td className="px-3 py-2">{PLATFORM_LABEL[e.platform]}</td>
                      <td className="px-3 py-2">{FORMAT_LABEL[e.format]}</td>
                      <td className="px-3 py-2">
                        {e.idea}
                        <span className="block text-xs text-muted">{e.theme}</span>
                      </td>
                    </tr>
                  )),
              )}
            </tbody>
          </table>
        </div>
      </Section>

      <Section title="Audience hypotheses">
        <ul className="flex flex-col gap-2">
          {c.audience_hypotheses.map((h, i) => (
            <li key={i} className="flex flex-wrap items-start gap-2 text-sm">
              <BasisBadge basis={h.basis} />
              <span>
                <span className="font-medium">{h.audience}:</span> {h.insight}
              </span>
            </li>
          ))}
        </ul>
      </Section>

      <Section title="How to measure">
        <ul className="flex flex-col gap-1 text-sm">
          {c.measurement.map((m, i) => (
            <li key={i}>
              <span className="font-medium">{m.metric}</span> on {PLATFORM_LABEL[m.platform]} —{" "}
              {m.why}
            </li>
          ))}
        </ul>
      </Section>

      <Section title="Assumptions">
        <ul className="flex flex-col gap-2">
          {c.assumptions.map((a, i) => (
            <li key={i} className="flex flex-wrap items-start gap-2 text-sm">
              <BasisBadge basis={a.basis} />
              <span>{a.statement}</span>
            </li>
          ))}
        </ul>
      </Section>

      {c.caveats.length > 0 && (
        <Section title="Caveats">
          <ul className="list-disc pl-5 text-sm text-muted">
            {c.caveats.map((cv, i) => (
              <li key={i}>{cv}</li>
            ))}
          </ul>
        </Section>
      )}
    </div>
  );
}
