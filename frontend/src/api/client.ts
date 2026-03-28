export type ApiError = Error & { status?: number };

function parseDetail(text: string, status: number): string {
  try {
    const j = JSON.parse(text) as { detail?: unknown };
    if (typeof j.detail === "string") {
      return j.detail;
    }
    if (j.detail !== undefined) {
      return String(j.detail);
    }
  } catch {
    return text.slice(0, 500) || `HTTP ${status}`;
  }
  return `HTTP ${status}`;
}

export function createApiFetch(apiBase: string) {
  return async function apiFetch<T>(
    path: string,
    init?: RequestInit,
  ): Promise<T | undefined> {
    const headers: Record<string, string> = {
      ...(init?.headers as Record<string, string> | undefined),
    };
    if (init?.body !== undefined) {
      headers["Content-Type"] = "application/json";
    }
    const url = `${apiBase}${path.startsWith("/") ? path : `/${path}`}`;
    const res = await fetch(url, {
      credentials: "same-origin",
      ...init,
      headers,
    });
    const text = await res.text();
    if (!res.ok) {
      const err = new Error(parseDetail(text, res.status)) as ApiError;
      err.status = res.status;
      throw err;
    }
    if (res.status === 204 || !text) {
      return undefined;
    }
    return JSON.parse(text) as T;
  };
}

export function buildQuery(
  params: Record<string, string | number | undefined | null>,
): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") {
      q.set(k, String(v));
    }
  }
  const s = q.toString();
  return s ? `?${s}` : "";
}
