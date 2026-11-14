import { describe, expect, test } from "vitest";

import { TAG_MAX_LENGTH } from "./api/constraints";
import { sanitizeTagInput } from "./tags";

describe("sanitizeTagInput", () => {
  test.each([
    ["Код", "код"],
    ["tag_1", "tag_1"],
    ["Ünïcödé", "ünïcödé"],
    ["sci-fi", "scifi"],
    ["c++", "c"],
    ["machine learning", "machinelearning"],
    ["#tag", "tag"],
    ["a.b,c", "abc"],
    ["", ""],
  ])("turns '%s' into '%s'", (raw, expected) => {
    expect(sanitizeTagInput(raw)).toBe(expected);
  });

  test("cuts the tag to the maximum length", () => {
    expect(sanitizeTagInput("a".repeat(TAG_MAX_LENGTH + 5))).toBe("a".repeat(TAG_MAX_LENGTH));
  });
});
