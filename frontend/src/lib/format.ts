const dateFormatter = new Intl.DateTimeFormat(undefined, { dateStyle: "medium" });
const dateTimeFormatter = new Intl.DateTimeFormat(undefined, {
  dateStyle: "medium",
  timeStyle: "short",
});

export function formatDate(value: string | Date | null | undefined): string {
  if (!value) return "—";
  return dateFormatter.format(typeof value === "string" ? new Date(value) : value);
}

export function formatDateTime(value: string | Date | null | undefined): string {
  if (!value) return "—";
  return dateTimeFormatter.format(typeof value === "string" ? new Date(value) : value);
}

/** Formats a metric value; `null` means "not reported", which is never shown as 0. */
export function formatMetric(value: number | null | undefined, unit = ""): string {
  if (value === null || value === undefined) return "Not available";
  const n = new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(value);
  return unit === "percent" ? `${n}%` : n;
}
