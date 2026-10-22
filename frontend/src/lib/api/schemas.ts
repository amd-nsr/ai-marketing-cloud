import { z } from "zod";

/** DRF page-number pagination envelope. */
export function paginated<T extends z.ZodType>(item: T) {
  return z.object({
    count: z.number(),
    next: z.string().nullable(),
    previous: z.string().nullable(),
    results: z.array(item),
  });
}

export type Paginated<T> = {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
};

export const emptySchema = z.null();
export const detailSchema = z.object({ detail: z.string() });
