import createClient from "openapi-fetch";

import type { paths } from "./schema";

/** Server-side bounds: 1..100. */
export const PAGE_SIZE = 20;

export type ApiError = Error & { status?: number };

type FetchResult<T> = {
  data?: T;
  error?: unknown;
  response: Response;
};

export const api = createClient<paths>({ credentials: "same-origin" });

function errorDetail(error: unknown, status: number): string {
  if (typeof error === "string") {
    return error.slice(0, 500) || `HTTP ${status}`;
  }
  if (error !== null && typeof error === "object" && "detail" in error) {
    const { detail } = error;
    return typeof detail === "string" ? detail : JSON.stringify(detail);
  }
  return `HTTP ${status}`;
}

/** Bridges openapi-fetch results to TanStack Query: data on 2xx, throw otherwise. */
export async function unwrap<T>(request: Promise<FetchResult<T>>): Promise<T> {
  const { data, error, response } = await request;
  if (!response.ok) {
    const err = new Error(errorDetail(error, response.status)) as ApiError;
    err.status = response.status;
    throw err;
  }
  return data as T;
}

