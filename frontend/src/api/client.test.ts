import { describe, expect, test } from "vitest";

import { type ApiError, unwrap } from "./client";

function result<T>(status: number, data?: T, error?: unknown) {
  return Promise.resolve({ data, error, response: new Response(null, { status }) });
}

async function rejection(promise: Promise<unknown>): Promise<ApiError> {
  try {
    await promise;
  } catch (err) {
    return err as ApiError;
  }
  throw new Error("expected a rejection");
}

describe("unwrap", () => {
  test("returns data on 2xx", async () => {
    await expect(unwrap(result(200, { id: "1" }))).resolves.toEqual({ id: "1" });
  });

  test("returns undefined on 204", async () => {
    await expect(unwrap(result(204))).resolves.toBeUndefined();
  });

  test("throws the string detail with the status", async () => {
    const err = await rejection(unwrap(result(404, undefined, { detail: "NotFoundError: gone" })));
    expect(err.message).toBe("NotFoundError: gone");
    expect(err.status).toBe(404);
  });

  test("serializes a non-string detail", async () => {
    const detail = [{ loc: ["body", "title"], msg: "required" }];
    const err = await rejection(unwrap(result(422, undefined, { detail })));
    expect(err.message).toBe(JSON.stringify(detail));
  });

  test("uses the raw text when the body is not JSON", async () => {
    const err = await rejection(unwrap(result(502, undefined, "Bad Gateway")));
    expect(err.message).toBe("Bad Gateway");
  });

  test("falls back to the status when there is no body", async () => {
    const err = await rejection(unwrap(result(500)));
    expect(err.message).toBe("HTTP 500");
  });
});
