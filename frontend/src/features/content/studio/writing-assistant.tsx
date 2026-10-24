"use client";

import { useState } from "react";

import { MockAIBadge } from "@/components/features/ai-badges";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { useOrg } from "@/hooks/use-org";
import { useWorkflowRun } from "@/hooks/use-workflow-run";
import { type AssistOperation, assistContent } from "@/lib/api/content";
import { errorMessage } from "@/lib/api/errors";
import { cn } from "@/lib/utils";

import { useStudioCapabilities } from "./queries";

export const LANGUAGES = [
  "English",
  "Arabic",
  "French",
  "Spanish",
  "German",
  "Portuguese",
  "Italian",
  "Turkish",
  "Hindi",
  "Urdu",
];

const TONES = ["Friendly", "Inspiring", "Funny", "Professional", "Urgent", "Calm"];
const LENGTHS = [
  { value: "short", label: "Short" },
  { value: "medium", label: "Medium" },
  { value: "long", label: "Long" },
] as const;

export interface AssistField {
  /** Form field name, e.g. "caption" or "slides.2.body". */
  name: string;
  /** Field kind sent to the API (headline, hook, caption, cta, script, slide). */
  kind: string;
  label: string;
}

function Chip({
  active,
  onClick,
  children,
  disabled,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      disabled={disabled}
      onClick={onClick}
      className={cn(
        "rounded-md border px-2.5 py-1 text-xs transition disabled:opacity-50",
        active
          ? "border-primary bg-primary text-primary-foreground"
          : "border-border bg-surface hover:bg-neutral-soft",
      )}
    >
      {children}
    </button>
  );
}

/**
 * The always-visible AI writing assistant beside the Write editor. It never saves: each
 * suggestion is inserted into (or appended to) the form, edited if needed, then saved
 * as a new version by the person.
 */
export function WritingAssistant({
  itemId,
  fields,
  field,
  onFieldChange,
  getText,
  getSelection,
  onApply,
  onHashtag,
  allowHashtags,
}: {
  itemId: string;
  fields: AssistField[];
  field: AssistField;
  onFieldChange: (field: AssistField) => void;
  getText: (name: string) => string;
  /** The selected part of the field, if the person selected text in it. */
  getSelection: (name: string) => { start: number; end: number } | null;
  onApply: (
    field: AssistField,
    text: string,
    mode: "replace" | "append",
    range?: { start: number; end: number },
  ) => void;
  onHashtag: (tag: string) => void;
  allowHashtags: boolean;
}) {
  const { organization } = useOrg();
  const caps = useStudioCapabilities();
  const [tone, setTone] = useState("");
  const [customTone, setCustomTone] = useState("");
  const [keywords, setKeywords] = useState("");
  const [length, setLength] = useState<"" | "short" | "medium" | "long">("");
  const [language, setLanguage] = useState("");
  const [runId, setRunId] = useState<string | null>(null);
  const [runField, setRunField] = useState<string | null>(null);
  const [operation, setOperation] = useState<AssistOperation>("draft");
  const [range, setRange] = useState<{ start: number; end: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Suggestions belong to the field they were made for; switching fields hides them.
  const run = useWorkflowRun(organization.id, runField === field.name ? runId : null);
  const working =
    runField === field.name &&
    runId !== null &&
    !run.data?.status.match(/succeeded|failed|cancelled/);
  const options =
    run.data?.status === "succeeded" ? ((run.data.output.options as string[]) ?? []) : null;
  const notes = (run.data?.output.notes as string[] | undefined) ?? [];
  const hasText = getText(field.name).trim().length > 0;

  if (caps.data && !caps.data.text_generation.available) {
    return (
      <p className="text-sm text-muted">
        AI writing isn&apos;t configured for this workspace. You can still write and edit everything
        by hand.
      </p>
    );
  }

  const run_ = async (op: AssistOperation) => {
    setError(null);
    const full = getText(field.name);
    const sel = op === "draft" ? null : getSelection(field.name);
    const text = sel ? full.slice(sel.start, sel.end) : full;
    if (op !== "draft" && !text.trim())
      return setError("Write something first, or use Write for me.");
    if (op === "translate" && !language) return setError("Choose a language to translate to.");
    const effectiveTone = tone === "custom" ? customTone.trim() : tone;
    try {
      const created = await assistContent(organization.id, itemId, {
        operation: op,
        field: field.kind,
        text,
        tone: effectiveTone,
        language: op === "translate" || op === "draft" || op === "rewrite" ? language : "",
        keywords: keywords
          .split(",")
          .map((k) => k.trim())
          .filter(Boolean)
          .slice(0, 10),
        length,
      });
      setOperation(op);
      setRange(sel);
      setRunField(field.name);
      setRunId(created.id);
    } catch (e) {
      setError(errorMessage(e));
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1.5">
        <label className="text-xs font-medium" htmlFor="assist-field">
          Working on
        </label>
        <Select
          id="assist-field"
          value={field.name}
          onChange={(e) => {
            const next = fields.find((f) => f.name === e.target.value);
            if (next) onFieldChange(next);
          }}
          className="h-8 text-sm"
        >
          {fields.map((f) => (
            <option key={f.name} value={f.name}>
              {f.label}
            </option>
          ))}
        </Select>
      </div>

      <div className="flex flex-col gap-1.5">
        <span className="text-xs font-medium">Tone</span>
        <div className="flex flex-wrap gap-1.5">
          <Chip active={tone === ""} onClick={() => setTone("")}>
            Brand voice
          </Chip>
          {TONES.map((t) => (
            <Chip key={t} active={tone === t} onClick={() => setTone(t)}>
              {t}
            </Chip>
          ))}
          <Chip active={tone === "custom"} onClick={() => setTone("custom")}>
            Custom…
          </Chip>
        </div>
        {tone === "custom" && (
          <Input
            aria-label="Custom tone"
            className="h-8"
            value={customTone}
            maxLength={100}
            placeholder="e.g. warm and a bit cheeky"
            onChange={(e) => setCustomTone(e.target.value)}
          />
        )}
      </div>

      <div className="flex flex-col gap-1.5">
        <label className="text-xs font-medium" htmlFor="assist-keywords">
          Keywords
        </label>
        <Input
          id="assist-keywords"
          className="h-8"
          value={keywords}
          placeholder="e.g. autumn, oat milk, weekend"
          onChange={(e) => setKeywords(e.target.value)}
        />
      </div>

      <div className="flex flex-col gap-3">
        <div className="flex flex-col gap-1.5">
          <span className="text-xs font-medium">Length</span>
          <div className="flex gap-1">
            {LENGTHS.map((l) => (
              <Chip
                key={l.value}
                active={length === l.value}
                onClick={() => setLength(length === l.value ? "" : l.value)}
              >
                {l.label}
              </Chip>
            ))}
          </div>
        </div>
        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-medium" htmlFor="assist-language">
            Language
          </label>
          <Select
            id="assist-language"
            className="h-8 text-xs"
            value={language}
            onChange={(e) => setLanguage(e.target.value)}
          >
            <option value="">Usual language</option>
            {LANGUAGES.map((l) => (
              <option key={l}>{l}</option>
            ))}
          </Select>
        </div>
      </div>

      <div className="flex flex-col gap-2">
        <Button onClick={() => void run_(hasText ? "rewrite" : "draft")} disabled={working}>
          {working
            ? "Writing…"
            : hasText
              ? `Rewrite ${field.label.toLowerCase()}`
              : "Write it for me"}
        </Button>
        <div className="flex flex-wrap gap-1.5" role="group" aria-label="Quick actions">
          {hasText && (
            <Button
              size="sm"
              variant="secondary"
              disabled={working}
              onClick={() => void run_("draft")}
            >
              Fresh ideas
            </Button>
          )}
          <Button
            size="sm"
            variant="secondary"
            disabled={working || !hasText}
            onClick={() => void run_("alternatives")}
          >
            More suggestions
          </Button>
          <Button
            size="sm"
            variant="secondary"
            disabled={working || !hasText}
            onClick={() => void run_("shorten")}
          >
            Shorten
          </Button>
          <Button
            size="sm"
            variant="secondary"
            disabled={working || !hasText}
            onClick={() => void run_("expand")}
          >
            Expand
          </Button>
          <Button
            size="sm"
            variant="secondary"
            disabled={working || !hasText}
            onClick={() => void run_("proofread")}
          >
            Fix grammar
          </Button>
          <Button
            size="sm"
            variant="secondary"
            disabled={working || !hasText}
            onClick={() => void run_("emoji")}
          >
            Add emojis
          </Button>
          <Button
            size="sm"
            variant="secondary"
            disabled={working || !hasText || !language}
            title={language ? `Translate to ${language}` : "Choose a language first"}
            onClick={() => void run_("translate")}
          >
            Translate
          </Button>
          {allowHashtags && (
            <Button
              size="sm"
              variant="secondary"
              disabled={working || !hasText}
              onClick={() => void run_("hashtags")}
            >
              Hashtags
            </Button>
          )}
        </div>
        <p className="text-xs text-muted">
          Tip: select part of the text in the editor to work on just that part.
        </p>
      </div>

      {error && <Alert tone="danger">{error}</Alert>}
      {run.data?.status === "failed" && <Alert tone="danger">{run.data.error_message}</Alert>}
      {working && (
        <p className="flex items-center gap-2 text-sm text-muted" aria-live="polite">
          <Spinner /> Writing suggestions…
        </p>
      )}
      {options && (
        <section aria-label="Suggestions" className="flex flex-col gap-2">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold">
              {operation === "hashtags" ? "Suggested hashtags" : "Suggestions"}
            </h3>
            <MockAIBadge isMock={Boolean(run.data?.is_mock)} />
          </div>
          {operation === "hashtags" ? (
            <div className="flex flex-wrap gap-1.5">
              {options.map((o) => (
                <button
                  key={o}
                  type="button"
                  onClick={() => onHashtag(o)}
                  className="rounded-full border border-border px-2.5 py-1 text-xs text-primary hover:border-primary"
                >
                  + #{o.replace(/^#/, "")}
                </button>
              ))}
            </div>
          ) : (
            <ul className="flex flex-col gap-2">
              {options.map((o, i) => (
                <li key={i} className="rounded-md border border-border p-3">
                  <p className="text-sm whitespace-pre-line">{o}</p>
                  <div className="mt-2 flex justify-end gap-1.5">
                    {!range && (
                      <Button size="sm" variant="ghost" onClick={() => onApply(field, o, "append")}>
                        Append
                      </Button>
                    )}
                    <Button
                      size="sm"
                      onClick={() => onApply(field, o, "replace", range ?? undefined)}
                    >
                      {range ? "Replace selection" : "Insert"}
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          )}
          {notes.map((n) => (
            <p key={n} className="text-xs text-muted">
              {n}
            </p>
          ))}
        </section>
      )}
    </div>
  );
}
