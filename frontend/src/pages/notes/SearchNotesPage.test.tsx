// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ContextMenuProvider } from "../../contexts/ContextMenuContext";
import { SearchNotesPage } from "./SearchNotesPage";

const MATERIAL_ID = "m1";
const ACTIVE_NOTE_ID = "note-active";
const DELETED_NOTE_ID = "note-deleted";

type Reply = { status: number; body?: unknown };
type ActionReplies = Record<string, Reply>;

function note(noteId: string, isDeleted: boolean) {
  return {
    note_id: noteId,
    material_id: MATERIAL_ID,
    title: null,
    content_html: `<p>${noteId} content</p>`,
    tags_html: "",
    link_html: "",
    chapter: "1",
    chapter_int: 1,
    page: 1,
    links_count: 0,
    is_deleted: isDeleted,
  };
}

const SEARCH_RESPONSE = {
  notes: [note(ACTIVE_NOTE_ID, false), note(DELETED_NOTE_ID, true)],
  total_count: 2,
  titles: { [MATERIAL_ID]: "Material" },
  material_types: { [MATERIAL_ID]: "book" },
  material_notes: { [MATERIAL_ID]: 2 },
  chapters: { [MATERIAL_ID]: ["1"] },
  query: null,
  tags: [],
  tags_query: null,
  next_token: null,
  page_size: 10,
  material_id: null,
};

const META_RESPONSE = { titles: { [MATERIAL_ID]: "Material" }, tags: [] };

function reply({ status, body }: Reply) {
  const text = body === undefined ? "" : JSON.stringify(body);
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    text: () => Promise.resolve(text),
  });
}

function stubFetch(actions: ActionReplies = {}) {
  const fetchMock = vi.fn((url: string, init?: RequestInit) => {
    const path = url.replace(/^\/api\/v1\/notes/, "").split("?")[0];
    if (path === "/meta") {
      return reply({ status: 200, body: META_RESPONSE });
    }
    if (path === "/search") {
      return reply({ status: 200, body: SEARCH_RESPONSE });
    }
    return reply(actions[`${init?.method ?? "GET"} ${path}`] ?? { status: 204 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderPage() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <MemoryRouter initialEntries={["/notes"]}>
      <QueryClientProvider client={qc}>
        <ContextMenuProvider>
          <SearchNotesPage />
        </ContextMenuProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

async function pickMenuItem(noteId: string, label: string) {
  await waitFor(() => {
    expect(document.getElementById(noteId)).not.toBeNull();
  });
  fireEvent.contextMenu(document.getElementById(noteId) as HTMLElement);
  fireEvent.click(await screen.findByText(label));
}

function actionCalls(fetchMock: ReturnType<typeof stubFetch>) {
  return fetchMock.mock.calls
    .filter(([, init]) => init?.method !== undefined)
    .map(([url, init]) => `${init?.method} ${url}`);
}

class NoopResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

beforeEach(() => {
  localStorage.clear();
  vi.stubGlobal("ResizeObserver", NoopResizeObserver);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("SearchNotesPage note actions", () => {
  it("deletes an active note through the API", async () => {
    const fetchMock = stubFetch();
    renderPage();

    await pickMenuItem(ACTIVE_NOTE_ID, "Delete");

    await waitFor(() => {
      expect(actionCalls(fetchMock)).toEqual([`DELETE /api/v1/notes/${ACTIVE_NOTE_ID}`]);
    });
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("restores a deleted note through the API", async () => {
    const fetchMock = stubFetch();
    renderPage();

    await pickMenuItem(DELETED_NOTE_ID, "Restore");

    await waitFor(() => {
      expect(actionCalls(fetchMock)).toEqual([
        `POST /api/v1/notes/${DELETED_NOTE_ID}/restore`,
      ]);
    });
  });

  it("shows a repeat queue failure until it is dismissed", async () => {
    const fetchMock = stubFetch({
      [`POST /${ACTIVE_NOTE_ID}/repeat-queue`]: {
        status: 503,
        body: { detail: "Kafka unavailable" },
      },
    });
    renderPage();

    await pickMenuItem(ACTIVE_NOTE_ID, "Insert to repeat queue");

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Kafka unavailable");
    expect(actionCalls(fetchMock)).toEqual([
      `POST /api/v1/notes/${ACTIVE_NOTE_ID}/repeat-queue`,
    ]);

    fireEvent.click(screen.getByRole("button", { name: "Dismiss error" }));

    await waitFor(() => {
      expect(screen.queryByRole("alert")).toBeNull();
    });
  });
});
