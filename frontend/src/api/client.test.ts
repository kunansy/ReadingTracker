import createClient from "openapi-fetch";
import { describe, expect, test, vi } from "vitest";

import { ApiError, unwrap, unwrapEmpty } from "./client";
import type { paths } from "./schema";

const MATERIAL_ID = "00000000-0000-0000-0000-000000000001";

function clientReturning(response: Response) {
  const fetch = vi.fn<(request: Request) => Promise<Response>>().mockResolvedValue(response);
  return { client: createClient<paths>({ baseUrl: "http://test", fetch }), fetch };
}

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

async function rejection(promise: Promise<unknown>): Promise<ApiError> {
  try {
    await promise;
  } catch (err) {
    if (err instanceof ApiError) {
      return err;
    }
    throw err;
  }
  throw new Error("expected a rejection");
}

describe("unwrap", () => {
  test("returns the body on 2xx", async () => {
    const { client } = clientReturning(json(200, { tags: ["a"] }));

    await expect(unwrap(client.GET("/api/v1/materials/tags"))).resolves.toEqual({ tags: ["a"] });
  });

  test("throws when a 2xx response has no body", async () => {
    const { client } = clientReturning(new Response(null, { status: 200 }));

    const err = await rejection(unwrap(client.GET("/api/v1/materials/tags")));

    expect(err.message).toBe("Empty response body");
    expect(err.status).toBe(200);
  });

  test("throws the string detail with the status", async () => {
    const { client } = clientReturning(json(404, { detail: "NotFoundError: gone" }));

    const err = await rejection(unwrap(client.GET("/api/v1/materials/tags")));

    expect(err.message).toBe("NotFoundError: gone");
    expect(err.status).toBe(404);
  });

  test("formats FastAPI validation errors", async () => {
    const detail = [
      { loc: ["query", "page_size"], msg: "Input should be less than or equal to 100", type: "x" },
      { loc: ["body"], msg: "Field required", type: "missing" },
    ];
    const { client } = clientReturning(json(422, { detail }));

    const err = await rejection(unwrap(client.GET("/api/v1/materials/tags")));

    expect(err.message).toBe("page_size: Input should be less than or equal to 100; Field required");
  });

  test("serializes an unknown detail shape", async () => {
    const { client } = clientReturning(json(400, { detail: { code: 7 } }));

    const err = await rejection(unwrap(client.GET("/api/v1/materials/tags")));

    expect(err.message).toBe('{"code":7}');
  });

  test("uses the raw text when the body is not JSON", async () => {
    const { client } = clientReturning(new Response("Bad Gateway", { status: 502 }));

    const err = await rejection(unwrap(client.GET("/api/v1/materials/tags")));

    expect(err.message).toBe("Bad Gateway");
    expect(err.status).toBe(502);
  });

  test("falls back to the status when there is no body", async () => {
    const { client } = clientReturning(new Response(null, { status: 500 }));

    const err = await rejection(unwrap(client.GET("/api/v1/materials/tags")));

    expect(err.message).toBe("HTTP 500");
  });

  test("omits undefined query params from the URL", async () => {
    const { client, fetch } = clientReturning(json(200, { tags: [] }));

    await unwrap(client.GET("/api/v1/notes/tags", { params: { query: { material_id: undefined } } }));

    const url = new URL(fetch.mock.calls[0][0].url);
    expect(url.pathname).toBe("/api/v1/notes/tags");
    expect(url.search).toBe("");
  });
});

describe("unwrapEmpty", () => {
  test("resolves on 204", async () => {
    const { client } = clientReturning(new Response(null, { status: 204 }));

    await expect(
      unwrapEmpty(
        client.POST("/api/v1/materials/{material_id}/outline", {
          params: { path: { material_id: MATERIAL_ID } },
        }),
      ),
    ).resolves.toBeUndefined();
  });

  test("throws on non-2xx", async () => {
    const { client } = clientReturning(json(409, { detail: "ConflictError: already outlined" }));

    const err = await rejection(
      unwrapEmpty(
        client.POST("/api/v1/materials/{material_id}/outline", {
          params: { path: { material_id: MATERIAL_ID } },
        }),
      ),
    );

    expect(err.message).toBe("ConflictError: already outlined");
    expect(err.status).toBe(409);
  });
});
