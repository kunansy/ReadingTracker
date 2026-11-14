// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { NotePage } from "./NotePage";

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

const NOTE_ID = "018e9dbe-1d3d-7a5a-b437-9bfa65171b42";
const LINKED_NOTE_ID = "1c2fc59d-5313-4615-9290-e8668abe2fc0";
const MATERIAL_ID = "2d3fc59d-5313-4615-9290-e8668abe2fc1";

function json(body: unknown, status = 200): Promise<Response> {
  return Promise.resolve(
    new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }),
  );
}

function stubFetch(note: { tags: string[]; link_id: string | null }) {
  vi.stubGlobal(
    "fetch",
    vi.fn((request: Request) => {
      const path = new URL(request.url).pathname;
      if (path === `/api/v1/notes/${NOTE_ID}`) {
        return json({
          note: {
            note_id: NOTE_ID,
            material_id: MATERIAL_ID,
            title: null,
            content: "content",
            added_at: "2026-11-14T00:00:00",
            chapter: "1",
            page: 1,
            is_deleted: false,
            note_number: 1,
            links_count: 0,
            ...note,
          },
        });
      }
      if (path === "/api/v1/notes/links") {
        return json({ link_to: null, links: [], next_token: null, page_size: 10 });
      }
      return json({ detail: "not stubbed" }, 404);
    }),
  );
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <MemoryRouter initialEntries={[`/notes/${NOTE_ID}`]}>
      <QueryClientProvider client={qc}>
        <Routes>
          <Route path="/notes/:noteId" element={<NotePage />} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("NotePage note references", () => {
  it("renders the tags and the linked note", async () => {
    stubFetch({ tags: ["a", "тег"], link_id: LINKED_NOTE_ID });
    renderPage();

    const tag = await screen.findByRole("link", { name: "#тег" });
    expect(tag.getAttribute("href")).toBe(`/notes?tags_query=${encodeURIComponent("тег")}`);
    expect(screen.getByRole("link", { name: "#a" })).toBeTruthy();
    const link = screen.getByRole("link", { name: `[[${LINKED_NOTE_ID}]]` });
    expect(link.getAttribute("href")).toBe(`/notes/${LINKED_NOTE_ID}`);
  });

  it("renders no references for a note without tags and link", async () => {
    stubFetch({ tags: [], link_id: null });
    renderPage();

    await screen.findByText("Note number: 1");

    expect(screen.queryByRole("link", { name: /^#/ })).toBeNull();
    expect(screen.queryByRole("link", { name: /^\[\[/ })).toBeNull();
  });
});
