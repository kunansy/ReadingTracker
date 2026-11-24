// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ContextMenuProvider } from "../../contexts/ContextMenuContext";
import { ListReadingMaterialsPage } from "./ListReadingMaterialsPage";

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

const MATERIAL_ID = "5c8a1f8e-3f2b-4c9a-9d6e-1a2b3c4d5e6f";
const COMPLETE_PATH = `/api/v1/materials/${MATERIAL_ID}/complete`;

const READING_PAGE = {
  next_token: null,
  total_count: 1,
  statistics: [
    {
      material: {
        material_id: MATERIAL_ID,
        title: "War and Peace",
        authors: "Tolstoy",
        pages: 1300,
        material_type: "book",
        tags: [],
        link: null,
        added_at: "2026-01-01T00:00:00",
        is_outlined: false,
      },
      started_at: "2026-01-02",
      duration: 10,
      lost_time: 0,
      total: 1300,
      percent_completed: 100,
      notes_count: 0,
      mean: 130,
      max_record: null,
      min_record: null,
    },
  ],
};

function stubFetch() {
  const fetchMock = vi.fn((request: Request) => {
    const path = new URL(request.url).pathname;
    if (path === "/api/v1/materials/reading") {
      return Promise.resolve(
        new Response(JSON.stringify(READING_PAGE), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    }
    if (path === COMPLETE_PATH) {
      return Promise.resolve(new Response(null, { status: 204 }));
    }
    return Promise.reject(new Error(`unexpected request: ${path}`));
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

async function completeBodies(fetchMock: ReturnType<typeof stubFetch>): Promise<unknown[]> {
  const requests = fetchMock.mock.calls
    .map(([request]) => request)
    .filter((request) => new URL(request.url).pathname === COMPLETE_PATH);
  return Promise.all(requests.map((request) => request.clone().json()));
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ContextMenuProvider>
        <MemoryRouter initialEntries={["/materials/reading"]}>
          <ListReadingMaterialsPage />
        </MemoryRouter>
      </ContextMenuProvider>
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
  HTMLDialogElement.prototype.showModal = vi.fn();
  HTMLDialogElement.prototype.close = vi.fn();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function openDialog() {
  await screen.findByText(/War and Peace/);
  clickButton("button.complete-material-open");
}

function confirm() {
  clickButton("#complete-material-confirm");
}

function clickButton(selector: string) {
  const button = document.querySelector<HTMLButtonElement>(selector);
  if (!button) {
    throw new Error(`button not found: ${selector}`);
  }
  fireEvent.click(button);
}

describe("ListReadingMaterialsPage complete dialog", () => {
  it("completes without an outline by default", async () => {
    const fetchMock = stubFetch();
    renderPage();

    await openDialog();
    confirm();

    await waitFor(async () => {
      const bodies = await completeBodies(fetchMock);
      expect(bodies).toHaveLength(1);
      expect(bodies[0]).toMatchObject({ is_outlined: false });
    });
  });

  it("sends the outline flag when the checkbox is ticked", async () => {
    const fetchMock = stubFetch();
    renderPage();

    await openDialog();
    fireEvent.click(screen.getByLabelText("With outline"));
    confirm();

    await waitFor(async () => {
      const bodies = await completeBodies(fetchMock);
      expect(bodies).toHaveLength(1);
      expect(bodies[0]).toMatchObject({ is_outlined: true });
    });
  });
});
