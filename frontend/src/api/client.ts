import createClient from "openapi-fetch";

import type { paths } from "./schema";

/** Server-side bounds: 1..100. */
export const PAGE_SIZE = 20;

const MAX_ERROR_TEXT_LENGTH = 500;

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

type FetchResult<T> =
  | { data: T; error?: never; response: Response }
  | { data?: never; error: unknown; response: Response };

export const api = createClient<paths>({ credentials: "same-origin" });

type ValidationIssue = { loc: (string | number)[]; msg: string };

function isValidationIssue(value: unknown): value is ValidationIssue {
  return (
    value !== null &&
    typeof value === "object" &&
    "loc" in value &&
    Array.isArray(value.loc) &&
    "msg" in value &&
    typeof value.msg === "string"
  );
}

function formatDetail(detail: unknown): string {
  if (typeof detail === "string") {
    return detail;
  }
  if (Array.isArray(detail) && detail.length > 0 && detail.every(isValidationIssue)) {
    return detail
      .map(({ loc, msg }) => {
        // FastAPI prefixes loc with the request part: "body", "query" or "path".
        const field = loc.slice(1).join(".");
        return field ? `${field}: ${msg}` : msg;
      })
      .join("; ");
  }
  return JSON.stringify(detail);
}

function errorDetail(error: unknown, status: number): string {
  if (typeof error === "string") {
    return error.slice(0, MAX_ERROR_TEXT_LENGTH) || `HTTP ${status}`;
  }
  if (error !== null && typeof error === "object" && "detail" in error) {
    return formatDetail(error.detail);
  }
  return `HTTP ${status}`;
}

export function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : "Unexpected error";
}

function assertOk(error: unknown, response: Response): void {
  if (!response.ok) {
    throw new ApiError(errorDetail(error, response.status), response.status);
  }
}

/** Resolves to the response body; throws `ApiError` on non-2xx or an empty body. */
export async function unwrap<T>(
  request: Promise<FetchResult<T>>,
): Promise<Exclude<T, undefined>> {
  const { data, error, response } = await request;
  assertOk(error, response);
  if (data === undefined) {
    throw new ApiError("Empty response body", response.status);
  }
  return data as Exclude<T, undefined>;
}

/** For endpoints without a response body (204); throws `ApiError` on non-2xx. */
export async function unwrapEmpty(request: Promise<FetchResult<unknown>>): Promise<void> {
  const { error, response } = await request;
  assertOk(error, response);
}
