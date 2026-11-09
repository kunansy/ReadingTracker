// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AddReadingLogPage } from "./AddReadingLogPage";

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

const READING_NOW_ID = "11111111-1111-1111-1111-111111111111";
const CHOSEN_ID = "22222222-2222-2222-2222-222222222222";
const COMPLETION_INFO_PATH = /^\/api\/v1\/materials\/([^/]+)\/completion-info$/;

function json(status: number, body: unknown): Promise<Response> {
  return Promise.resolve(
    new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }),
  );
}

function stubFetch(readingNowId: string | null) {
  const fetchMock = vi.fn((request: Request) => {
    const path = new URL(request.url).pathname;
    if (path === "/api/v1/reading_logs/material-reading-now") {
      return json(200, { material_id: readingNowId });
    }
    if (path === "/api/v1/materials/reading-titles") {
      return json(200, { items: { [READING_NOW_ID]: "Reading now", [CHOSEN_ID]: "Chosen" } });
    }
    if (COMPLETION_INFO_PATH.test(path)) {
      return json(200, { material_pages: 100, material_type: "book", pages_read: 10, read_days: 1 });
    }
    return json(404, { detail: `unexpected ${path}` });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function completionInfoMaterialIds(fetchMock: ReturnType<typeof stubFetch>): string[] {
  return fetchMock.mock.calls
    .map(([request]) => COMPLETION_INFO_PATH.exec(new URL(request.url).pathname)?.[1])
    .filter((id): id is string => id !== undefined);
}

function renderPage(url = "/reading_logs/add-view") {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <MemoryRouter initialEntries={[url]}>
      <QueryClientProvider client={qc}>
        <AddReadingLogPage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AddReadingLogPage material selection", () => {
  it("selects the material being read now", async () => {
    const fetchMock = stubFetch(READING_NOW_ID);
    renderPage();

    await waitFor(() => {
      expect(completionInfoMaterialIds(fetchMock)).toEqual([READING_NOW_ID]);
    });
  });

  it("leaves the material empty when none is being read", async () => {
    const fetchMock = stubFetch(null);
    renderPage();

    expect(await screen.findByText("Add reading log")).not.toBeNull();
    expect(screen.queryByText(/Failed to load/)).toBeNull();
    expect(completionInfoMaterialIds(fetchMock)).toEqual([]);
  });

  it("prefers the material chosen in the URL", async () => {
    const fetchMock = stubFetch(READING_NOW_ID);
    renderPage(`/reading_logs/add-view?material_id=${CHOSEN_ID}`);

    expect(await screen.findByText("Add reading log")).not.toBeNull();
    expect(completionInfoMaterialIds(fetchMock)).toEqual([CHOSEN_ID]);
  });
});
