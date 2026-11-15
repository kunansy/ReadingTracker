// @vitest-environment jsdom
import { cleanup, screen } from "@testing-library/react";
import { afterEach, describe, it, vi } from "vitest";

import {
  FULL_TAGS,
  expectNoTagIsCreatedOnceFull,
  expectTagInputIsSanitized,
  renderPage,
  stubGetRoutes,
} from "../../test/tagInput";
import { UpdateNotePage } from "./UpdateNotePage";

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

const NOTE_ID = "22222222-2222-2222-2222-222222222222";
const MATERIAL_ID = "11111111-1111-1111-1111-111111111111";

const NOTE = {
  note_id: NOTE_ID,
  material_id: MATERIAL_ID,
  title: null,
  content: "Content",
  chapter: "",
  page: 1,
  tags: [],
  link_id: null,
  links_count: 0,
  note_number: 1,
  added_at: "2026-01-01T00:00:00",
  is_deleted: false,
};

function stubNote(tags: readonly string[]) {
  stubGetRoutes({
    [`/api/v1/notes/${NOTE_ID}`]: { note: { ...NOTE, tags } },
    "/api/v1/notes/tags": { tags: [] },
    "/api/v1/notes/possible-links": { items: [] },
    "/api/v1/materials/titles": { items: { [MATERIAL_ID]: "Title" } },
  });
}

async function renderNotePage() {
  renderPage(<UpdateNotePage />, `/notes/update?note_id=${NOTE_ID}`);
  await screen.findByDisplayValue(NOTE.content);
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("UpdateNotePage tags", () => {
  it("sanitizes the typed tag and says so", async () => {
    stubNote([]);
    await renderNotePage();

    await expectTagInputIsSanitized();
  });

  it("does not create a tag past the maximum", async () => {
    stubNote(FULL_TAGS);
    await renderNotePage();

    await expectNoTagIsCreatedOnceFull();
  });
});
