// @vitest-environment jsdom
import { cleanup, fireEvent, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  FULL_TAGS,
  expectNoTagIsCreatedOnceFull,
  expectTagInputIsSanitized,
  json,
  renderPage as renderWithClient,
  stubGetRoutes,
} from "../../test/tagInput";
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
  tags: [],
  link: null,
  added_at: "2026-01-01T00:00:00",
  is_outlined: false,
};

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

const PAGE_URL = `/materials/update?material_id=${MATERIAL_ID}`;

function renderPage() {
  renderWithClient(<UpdateMaterialPage />, PAGE_URL);
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

describe("UpdateMaterialPage tags", () => {
  async function renderLoadedPage() {
    renderPage();
    await screen.findByDisplayValue(MATERIAL.title);
  }

  function stubMaterial(tags: readonly string[]) {
    stubGetRoutes({
      "/api/v1/materials/tags": { tags: [] },
      [`/api/v1/materials/${MATERIAL_ID}`]: { material: { ...MATERIAL, tags } },
    });
  }

  it("sanitizes the typed tag and says so", async () => {
    stubMaterial([]);
    await renderLoadedPage();

    await expectTagInputIsSanitized();
  });

  it("does not create a tag past the maximum", async () => {
    stubMaterial(FULL_TAGS);
    await renderLoadedPage();

    await expectNoTagIsCreatedOnceFull();
  });
});
