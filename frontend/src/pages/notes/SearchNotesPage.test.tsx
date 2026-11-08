// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ContextMenuProvider } from "../../contexts/ContextMenuContext";
import { SearchNotesPage } from "./SearchNotesPage";

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

function reply({ status, body }: Reply): Promise<Response> {
  const payload = body === undefined ? null : JSON.stringify(body);
  return Promise.resolve(
    new Response(payload, { status, headers: { "Content-Type": "application/json" } }),
  );
}

function stubFetch(actions: ActionReplies = {}) {
  const fetchMock = vi.fn((request: Request) => {
    const path = new URL(request.url).pathname.replace(/^\/api\/v1\/notes/, "");
    if (path === "/meta") {
      return reply({ status: 200, body: META_RESPONSE });
    }
    if (path === "/search") {
      return reply({ status: 200, body: SEARCH_RESPONSE });
    }
    return reply(actions[`${request.method} ${path}`] ?? { status: 204 });
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
    .map(([request]) => request)
    .filter((request) => request.method !== "GET")
    .map((request) => `${request.method} ${new URL(request.url).pathname}`);
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

describe("SearchNotesPage query autocompletion", () => {
  async function typeQuery(value: string) {
    const input = await screen.findByPlaceholderText("Enter a query");
    fireEvent.change(input, { target: { value } });
    fireEvent.keyDown(input, { key: "a" });
  }

  function hints(): string[] {
    const options = document.querySelectorAll("#search-note-hints option");
    return Array.from(options, (option) => option.getAttribute("value") ?? "");
  }

  it("lists the suggestions", async () => {
    stubFetch({
      "GET /autocompletion": { status: 200, body: { autocompletions: ["alpha", "beta"] } },
    });
    renderPage();

    await typeQuery("al");

    await waitFor(() => {
      expect(hints()).toEqual(["alpha", "beta"]);
    });
  });

  it.each([
    ["a failed request", { status: 500, body: { detail: "boom" } }],
    ["an empty body", { status: 200 }],
  ])("clears the suggestions and reports %s", async (_name, failure: Reply) => {
    const actions: ActionReplies = {
      "GET /autocompletion": { status: 200, body: { autocompletions: ["alpha"] } },
    };
    stubFetch(actions);
    renderPage();
    await typeQuery("al");
    await waitFor(() => {
      expect(hints()).toEqual(["alpha"]);
    });

    actions["GET /autocompletion"] = failure;
    await typeQuery("alp");

    await waitFor(() => {
      expect(hints()).toEqual([]);
    });
    expect((await screen.findByRole("alert")).textContent).toContain("Autocomplete unavailable");
  });

  it("hides the autocomplete error after a successful request", async () => {
    const actions: ActionReplies = {
      "GET /autocompletion": { status: 500, body: { detail: "boom" } },
    };
    stubFetch(actions);
    renderPage();
    await typeQuery("al");
    expect((await screen.findByRole("alert")).textContent).toContain("boom");

    actions["GET /autocompletion"] = { status: 200, body: { autocompletions: ["alpha"] } };
    await typeQuery("alp");

    await waitFor(() => {
      expect(hints()).toEqual(["alpha"]);
    });
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
