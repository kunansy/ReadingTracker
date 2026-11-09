// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ListCompletedMaterialsPage } from "./ListCompletedMaterialsPage";

vi.mock("../../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/client")>();
  const { default: createClient } = await import("openapi-fetch");
  return {
    ...actual,
    api: createClient<import("../../api/schema").paths>({
      baseUrl: "http://localhost",
      fetch: (request) => globalThis.fetch(request),
    }),
  };
});

const COMPLETED_PATH = "/api/v1/materials/completed";

function json(body: unknown): Promise<Response> {
  return Promise.resolve(
    new Response(JSON.stringify(body), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

function stubFetch() {
  const fetchMock = vi.fn((request: Request) => {
    const path = new URL(request.url).pathname;
    if (path === "/api/v1/materials/tags") {
      return json({ tags: [] });
    }
    if (path === COMPLETED_PATH) {
      return json({ statistics: [], next_token: null, total_count: 0 });
    }
    return Promise.reject(new Error(`unexpected request: ${path}`));
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function completedQueries(fetchMock: ReturnType<typeof stubFetch>): URLSearchParams[] {
  return fetchMock.mock.calls
    .map(([request]) => new URL(request.url))
    .filter((url) => url.pathname === COMPLETED_PATH)
    .map((url) => url.searchParams);
}

function renderPage(search = "") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[`/materials/completed${search}`]}>
        <ListCompletedMaterialsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

class NoopResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

beforeEach(() => {
  vi.stubGlobal("ResizeObserver", NoopResizeObserver);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("ListCompletedMaterialsPage outlined filter", () => {
  it("omits is_outlined when no filter is chosen", async () => {
    const fetchMock = stubFetch();

    renderPage();

    await waitFor(() => expect(completedQueries(fetchMock)).not.toHaveLength(0));
    expect(completedQueries(fetchMock).at(-1)?.has("is_outlined")).toBe(false);
  });

  it("passes is_outlined from the URL to the API", async () => {
    const fetchMock = stubFetch();

    renderPage("?is_outlined=false");

    await waitFor(() =>
      expect(completedQueries(fetchMock).at(-1)?.get("is_outlined")).toBe("false"),
    );
  });

  it("sends is_outlined=true after choosing Outlined only", async () => {
    const fetchMock = stubFetch();
    renderPage();
    await screen.findByLabelText("Outlined only");

    fireEvent.click(screen.getByLabelText("Outlined only"));

    await waitFor(() =>
      expect(completedQueries(fetchMock).at(-1)?.get("is_outlined")).toBe("true"),
    );
  });
});
