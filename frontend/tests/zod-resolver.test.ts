import { describe, expect, it } from "vitest";
import { z } from "zod";

import { zodResolver } from "@/lib/validation/zod-resolver";

describe("zodResolver", () => {
  const schema = z.object({ email: z.string().email("Bad email"), age: z.number().min(18) });
  const resolve = zodResolver(schema);

  it("returns parsed values on success", async () => {
    const result = await resolve({ email: "a@b.co", age: 20 }, undefined, {} as never);
    expect(result).toEqual({ values: { email: "a@b.co", age: 20 }, errors: {} });
  });

  it("maps issues to field errors (first per field)", async () => {
    const result = await resolve({ email: "nope", age: 3 }, undefined, {} as never);
    expect(result.values).toEqual({});
    expect(result.errors).toMatchObject({
      email: { message: "Bad email" },
      age: { type: "too_small" },
    });
  });
});

describe("zodResolver nested paths", () => {
  it("nests array and object errors the way react-hook-form expects", async () => {
    const schema = z.object({
      items: z.array(z.object({ name: z.string().min(1, "Name required") })),
    });
    const result = await zodResolver(schema)(
      { items: [{ name: "ok" }, { name: "" }] },
      undefined,
      {} as never,
    );
    const errors = result.errors as unknown as {
      items: Array<{ name?: { message: string } } | undefined>;
    };
    expect(errors.items[1]?.name?.message).toBe("Name required");
    expect(errors.items[0]).toBeUndefined();
  });
});
