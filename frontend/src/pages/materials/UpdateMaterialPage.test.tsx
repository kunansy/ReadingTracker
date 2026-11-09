// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { UpdateMaterialPage } from "./UpdateMaterialPage";

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

const MATERIAL_ID = "11111111-1111-1111-1111-111111111111";

const MATERIAL = {
  material_id: MATERIAL_ID,
  title: "Title",
  authors: "Author",
  pages: 100,
  material_type: "book",
  tags: null,
  link: null,
  added_at: "2026-01-01T00:00:00",
  is_outlined: false,
};

function json(status: number, body: unknown): Promise<Response> {
  return Promise.resolve(
    new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }),
  );
}

function stubFetch(patchReply: () => Promise<Response>) {
  const fetchMock = vi.fn((request: Request) => {
    const path = new URL(request.url).pathname;
    if (request.method === "PATCH") {
      return patchReply();
    }
    if (path === "/api/v1/materials/tags") {
      return json(200, { tags: [] });
    }
    if (path === `/api/v1/materials/${MATERIAL_ID}`) {
      return json(200, { material: MATERIAL });
    }
    return json(404, { detail: `unexpected ${path}` });
  });
  vi.stubGlobal("fetch", fetchMock);
}

function renderPage() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <MemoryRouter initialEntries={[`/materials/update?material_id=${MATERIAL_ID}`]}>
      <QueryClientProvider client={qc}>
        <UpdateMaterialPage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("UpdateMaterialPage", () => {
  it("shows the error when the update is rejected", async () => {
    stubFetch(() => json(400, { detail: "Pages must be positive" }));
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "Update" }));

    expect(await screen.findByText("Pages must be positive")).not.toBeNull();
  });
});
