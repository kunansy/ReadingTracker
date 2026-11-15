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
import { AddMaterialPage } from "./AddMaterialPage";

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
  stubGetRoutes({
    "/api/v1/materials/tags": { tags: [] },
    "/api/v1/materials/authors": { authors: [] },
  });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AddMaterialPage tags", () => {
  it("sanitizes the typed tag and says so", async () => {
    renderPage(<AddMaterialPage />, "/materials/add");

    await expectTagInputIsSanitized();
  });

  it("does not create a tag past the maximum", async () => {
    renderPage(<AddMaterialPage />, "/materials/add");

    await addTags(FULL_TAGS);

    await expectNoTagIsCreatedOnceFull();
  });
});
