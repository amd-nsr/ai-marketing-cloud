import type { FieldValues, Path, UseFormSetError } from "react-hook-form";

import { ApiError } from "@/lib/api/errors";

/** Copies backend field errors onto the form; returns any remaining general message. */
export function applyServerErrors<T extends FieldValues>(
  error: unknown,
  setError: UseFormSetError<T>,
  fields: readonly string[],
): string | null {
  if (!(error instanceof ApiError)) return "Something went wrong. Please try again.";
  const fieldErrors = error.fieldErrors;
  let unmatched: string | null = null;
  for (const [field, message] of Object.entries(fieldErrors)) {
    if (fields.includes(field)) setError(field as Path<T>, { type: "server", message });
    else unmatched ??= message;
  }
  if (Object.keys(fieldErrors).length === 0) return error.message;
  return unmatched;
}
