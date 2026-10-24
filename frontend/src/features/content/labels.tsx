import { Badge, type BadgeTone } from "@/components/ui/badge";
import type { Platform } from "@/lib/api/brand";
import type {
  ContentFormat,
  ContentPlatform,
  ContentStatus,
  DocumentKind,
} from "@/lib/api/content";

export const PLATFORM_LABEL: Record<ContentPlatform, string> = {
  instagram: "Instagram",
  facebook: "Facebook",
  tiktok: "TikTok",
  blog: "Blog",
  email: "Email",
};

/** Platforms with a publishing integration (blog and email are written here, then exported). */
export const SOCIAL_PLATFORMS: Platform[] = ["instagram", "facebook", "tiktok"];
export const isSocial = (p: ContentPlatform): p is Platform =>
  (SOCIAL_PLATFORMS as string[]).includes(p);

export const FORMAT_LABEL: Record<ContentFormat, string> = {
  post: "Post",
  carousel: "Carousel",
  reel: "Reel",
  story: "Story",
  short_video: "Short video",
  article: "Article",
  newsletter: "Newsletter",
};

/** Mirrors backend apps/content/platform_rules.py (server remains authoritative). */
export const PLATFORM_FORMATS: Record<ContentPlatform, ContentFormat[]> = {
  instagram: ["post", "carousel", "reel", "story"],
  facebook: ["post", "carousel", "reel", "story"],
  tiktok: ["short_video", "carousel"],
  blog: ["article"],
  email: ["newsletter"],
};
export const CAPTION_LIMIT: Record<ContentPlatform, number> = {
  instagram: 2200,
  facebook: 63206,
  tiktok: 2200,
  blog: 100000,
  email: 50000,
};

/** Mirrors backend documents.DOCUMENT_KIND_FOR_FORMAT. */
export const DOCUMENT_KIND: Partial<Record<ContentFormat, DocumentKind>> = {
  post: "design",
  story: "design",
  carousel: "carousel",
  reel: "video",
  short_video: "video",
};

export const STATUS_META: Record<ContentStatus, { label: string; tone: BadgeTone }> = {
  draft: { label: "Draft", tone: "neutral" },
  in_review: { label: "Awaiting approval", tone: "info" },
  changes_requested: { label: "Changes requested", tone: "warning" },
  approved: { label: "Approved", tone: "success" },
  scheduled: { label: "Scheduled", tone: "info" },
  published: { label: "Published", tone: "success" },
  archived: { label: "Archived", tone: "neutral" },
};

export function StatusBadge({ status }: { status: ContentStatus }) {
  const meta = STATUS_META[status];
  return <Badge tone={meta.tone}>{meta.label}</Badge>;
}

export function PlatformBadge({
  platform,
  format,
}: {
  platform: ContentPlatform;
  format?: ContentFormat;
}) {
  return (
    <Badge>
      {PLATFORM_LABEL[platform]}
      {format && ` · ${FORMAT_LABEL[format]}`}
    </Badge>
  );
}

export function IssueSummary({ checks }: { checks: { severity: "error" | "warning" }[] }) {
  const errors = checks.filter((c) => c.severity === "error").length;
  const warnings = checks.length - errors;
  if (!checks.length) return <span className="text-xs text-success">✓ Checks passed</span>;
  return (
    <span className="text-xs">
      {errors > 0 && <span className="text-danger">{errors} to fix</span>}
      {errors > 0 && warnings > 0 && <span className="text-muted"> · </span>}
      {warnings > 0 && (
        <span className="text-warning">
          {warnings} warning{warnings > 1 ? "s" : ""}
        </span>
      )}
    </span>
  );
}
