// @vitest-environment jsdom
import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach, describe, it, vi } from "vitest";

import {
  FULL_TAGS,
  addTags,
  expectNoTagIsCreatedOnceFull,
  expectTagInputIsSanitized,
  renderPage,
  stubGetRoutes,
} from "../../test/tagInput";
import { AddNotePage } from "./AddNotePage";

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

beforeEach(() => {
  localStorage.clear();
  stubGetRoutes({
    "/api/v1/notes/tags": { tags: [] },
    "/api/v1/materials/titles": { items: { "11111111-1111-1111-1111-111111111111": "Title" } },
  });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AddNotePage tags", () => {
  it("sanitizes the typed tag and says so", async () => {
    renderPage(<AddNotePage />, "/notes/add");

    await expectTagInputIsSanitized();
  });

  it("does not create a tag past the maximum", async () => {
    renderPage(<AddNotePage />, "/notes/add");

    await addTags(FULL_TAGS);

    await expectNoTagIsCreatedOnceFull();
  });
});
