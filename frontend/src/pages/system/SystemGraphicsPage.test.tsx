// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SystemGraphicsPage } from "./SystemGraphicsPage";

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
const READING_PROGRESS_PATH = "/api/v1/system/graphics/reading-progress";

type Reply = { status: number; body?: unknown };

const SPAN = {
  total: 2,
  would_be_total: 3,
  zero_days: 1,
  mean: 0.67,
  median: 1,
  max_record: { date: "2026-01-03", amount: 1 },
  min_record: { date: "2026-01-02", amount: 0 },
};

const SUMMARY_RESPONSE = {
  tracker_statistics: {
    started_at: "2026-01-01",
    finished_at: "2026-01-03",
    duration: 3,
    lost_time: 1,
    mean: 1.5,
    median: 1,
    pages_read: { book: 2 },
    materials_completed: {},
    total_materials_completed: 0,
    would_be_total: 3,
    min_log_record: null,
    max_log_record: null,
    duration_period: "3 days",
    total_pages_read: 2,
    lost_time_period: "1 day",
    lost_time_percent: 33.33,
    would_be_total_percent: 150,
  },
  reading_trend: SPAN,
  notes_trend: SPAN,
  completed_materials_trend: SPAN,
  repeated_materials_trend: SPAN,
  outlined_materials_trend: SPAN,
};

function reply({ status, body }: Reply): Promise<Response> {
  const payload = body === undefined ? null : JSON.stringify(body);
  return Promise.resolve(
    new Response(payload, { status, headers: { "Content-Type": "application/json" } }),
  );
}

function stubFetch(overrides: Record<string, Reply> = {}) {
  const fetchMock = vi.fn((request: Request) => {
    const path = new URL(request.url).pathname;
    const override = overrides[path];
    if (override) {
      return reply(override);
    }
    if (path === "/api/v1/reading_logs/material-reading-now") {
      return reply({ status: 200, body: { material_id: READING_NOW_ID } });
    }
    if (path === "/api/v1/materials/read-titles") {
      return reply({
        status: 200,
        body: { items: { [READING_NOW_ID]: "Reading now", [CHOSEN_ID]: "Chosen" } },
      });
    }
    if (path === "/api/v1/system/summary") {
      return reply({ status: 200, body: SUMMARY_RESPONSE });
    }
    return reply({ status: 200, body: { image: "" } });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function readingProgressMaterialIds(fetchMock: ReturnType<typeof stubFetch>): string[] {
  return fetchMock.mock.calls
    .map(([request]) => new URL(request.url))
    .filter((url) => url.pathname === READING_PROGRESS_PATH)
    .map((url) => url.searchParams.get("material_id") ?? "");
}

function renderPage(url = "/system/graphics") {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <MemoryRouter initialEntries={[url]}>
      <QueryClientProvider client={qc}>
        <SystemGraphicsPage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("SystemGraphicsPage reading progress", () => {
  it("loads the progress of the material being read now", async () => {
    const fetchMock = stubFetch();
    renderPage();

    expect(await screen.findByText("Reading progress")).not.toBeNull();
    await waitFor(() => {
      expect(readingProgressMaterialIds(fetchMock)).toEqual([READING_NOW_ID]);
    });
  });

  it("asks to select a material when none is being read", async () => {
    const fetchMock = stubFetch({
      "/api/v1/reading_logs/material-reading-now": { status: 200, body: { material_id: null } },
    });
    renderPage();

    expect(await screen.findByText("Tracker statistics")).not.toBeNull();
    expect(screen.getByText("Select a material to see reading progress.")).not.toBeNull();
    expect(readingProgressMaterialIds(fetchMock)).toEqual([]);
  });

  it("prefers the material chosen in the URL", async () => {
    const fetchMock = stubFetch();
    renderPage(`/system/graphics?material_id=${CHOSEN_ID}`);

    expect(await screen.findByText("Reading progress")).not.toBeNull();
    await waitFor(() => {
      expect(readingProgressMaterialIds(fetchMock)).toEqual([CHOSEN_ID]);
    });
  });
});

describe("SystemGraphicsPage tracker statistics", () => {
  it("shows the statistics of a non-empty reading log", async () => {
    stubFetch();
    renderPage();

    expect(await screen.findByText("First record date: 2026-01-01")).not.toBeNull();
    expect(screen.queryByText("Reading log is empty.")).toBeNull();
  });

  it("says the reading log is empty when there are no statistics", async () => {
    stubFetch({
      "/api/v1/system/summary": {
        status: 200,
        body: { ...SUMMARY_RESPONSE, tracker_statistics: null },
      },
    });
    renderPage();

    expect(await screen.findByText("Reading log is empty.")).not.toBeNull();
    expect(screen.getByText("Tracker statistics")).not.toBeNull();
    expect(screen.queryByText(/First record date/)).toBeNull();
  });
});

describe("SystemGraphicsPage graphics", () => {
  it("shows a failed graphic as an error, not as missing data", async () => {
    stubFetch({
      "/api/v1/system/graphics/outline-percentage": { status: 500, body: { detail: "boom" } },
    });
    renderPage();

    const section = (await screen.findByText("Outline percentage")).closest("section");
    if (!section) {
      throw new Error("graphic section not found");
    }
    await waitFor(() => {
      expect(section.textContent).toContain("Error: boom");
    });
    expect(section.textContent).not.toContain("No graphic data available");
  });
});

describe("SystemGraphicsPage material titles", () => {
  it("reports a failed titles request and still renders the statistics", async () => {
    stubFetch({
      "/api/v1/materials/read-titles": { status: 500, body: { detail: "boom" } },
    });
    renderPage();

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Failed to load materials: boom");
    expect(await screen.findByText("Tracker statistics")).not.toBeNull();
  });
});
