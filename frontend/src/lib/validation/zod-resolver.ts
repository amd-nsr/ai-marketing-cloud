import type { FieldErrors, FieldValues, Resolver } from "react-hook-form";
import type { z } from "zod";

type ErrorTree = Record<string | number, unknown>;

/** Writes `error` at `path` inside a nested object, keeping the first error per field. */
function setAtPath(
  tree: ErrorTree,
  path: (string | number)[],
  error: { type: string; message: string },
) {
  let node = tree;
  path.forEach((segment, i) => {
    if (i === path.length - 1) {
      node[segment] ??= error;
      return;
    }
    const next = node[segment];
    if (typeof next !== "object" || next === null || "message" in (next as object)) {
      node[segment] = typeof path[i + 1] === "number" ? [] : {};
    }
    node = node[segment] as ErrorTree;
  });
}

/** Minimal react-hook-form resolver for zod schemas (avoids an extra dependency). */
export function zodResolver<TValues extends FieldValues>(
  schema: z.ZodType<TValues>,
): Resolver<TValues> {
  return async (values) => {
    const result = await schema.safeParseAsync(values);
    if (result.success) return { values: result.data, errors: {} };
    const errors: ErrorTree = {};
    for (const issue of result.error.issues) {
      const path = issue.path.length ? (issue.path as (string | number)[]) : ["root"];
      setAtPath(errors, path, { type: issue.code, message: issue.message });
    }
    return { values: {}, errors: errors as unknown as FieldErrors<TValues> };
  };
}
