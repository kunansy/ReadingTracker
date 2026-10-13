import { describe, expect, test } from "vitest";

import { parseNoteDraft, resolveNoteDraft } from "./noteDraft.ts";

const MATERIAL_A = "11111111-1111-1111-1111-111111111111";
const MATERIAL_B = "22222222-2222-2222-2222-222222222222";

describe("parseNoteDraft", () => {
  test("returns the draft when every field has the expected type", () => {
    const stored = { materialId: MATERIAL_A, chapter: "3", page: 42 };

    expect(parseNoteDraft(stored)).toEqual(stored);
  });

  test("drops fields that are not part of the draft", () => {
    const stored = { materialId: MATERIAL_A, chapter: "3", page: 42, title: "stale" };

    expect(parseNoteDraft(stored)).toEqual({ materialId: MATERIAL_A, chapter: "3", page: 42 });
  });

  test.each([
    ["null", null],
    ["a string", "draft"],
    ["a numeric materialId", { materialId: 123, chapter: "3", page: 42 }],
    ["a missing chapter", { materialId: MATERIAL_A, page: 42 }],
    ["a numeric chapter", { materialId: MATERIAL_A, chapter: 3, page: 42 }],
    ["a string page", { materialId: MATERIAL_A, chapter: "3", page: "42" }],
    ["a missing page", { materialId: MATERIAL_A, chapter: "3" }],
    ["a NaN page", { materialId: MATERIAL_A, chapter: "3", page: Number.NaN }],
  ])("returns null for %s", (_name, stored) => {
    expect(parseNoteDraft(stored)).toBeNull();
  });
});

describe("resolveNoteDraft", () => {
  test("returns an empty draft when there is no query material and no stored draft", () => {
    expect(resolveNoteDraft("", null)).toEqual({ materialId: "", chapter: "", page: 0 });
  });

  test("restores the stored draft when there is no query material", () => {
    const draft = { materialId: MATERIAL_A, chapter: "3", page: 42 };

    expect(resolveNoteDraft("", draft)).toEqual(draft);
  });

  test("restores chapter and page when the query material matches the draft", () => {
    const draft = { materialId: MATERIAL_A, chapter: "3", page: 42 };

    expect(resolveNoteDraft(MATERIAL_A, draft)).toEqual(draft);
  });

  test("keeps the query material and drops chapter and page of another material", () => {
    const draft = { materialId: MATERIAL_A, chapter: "3", page: 42 };

    expect(resolveNoteDraft(MATERIAL_B, draft)).toEqual({ materialId: MATERIAL_B, chapter: "", page: 0 });
  });

  test("uses the query material when there is no stored draft", () => {
    expect(resolveNoteDraft(MATERIAL_B, null)).toEqual({ materialId: MATERIAL_B, chapter: "", page: 0 });
  });
});
