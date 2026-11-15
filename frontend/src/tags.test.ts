import { describe, expect, test } from "vitest";

import { TAG_MAX_LENGTH } from "./api/constraints";
import { TAG_LENGTH_NOTICE, TAG_SEPARATOR_NOTICE, sanitizeTagInput, toTag } from "./tags";

describe("sanitizeTagInput", () => {
  test.each([
    ["Код", "код"],
    ["tag_1", "tag_1"],
    ["Ünïcödé", "ünïcödé"],
    ["", ""],
  ])("keeps '%s' as '%s' without a notice", (raw, expected) => {
    expect(sanitizeTagInput(raw)).toEqual({ value: expected, notice: null });
  });

  test.each([
    ["sci-fi", "sci_fi"],
    ["machine learning", "machine_learning"],
    ["a -- b", "a_b"],
    ["c++", "c_"],
    ["#tag", "tag"],
    ["a.b,c", "a_b_c"],
    ["-", ""],
  ])("turns the separators in '%s' into '%s' with a notice", (raw, expected) => {
    expect(sanitizeTagInput(raw)).toEqual({ value: expected, notice: TAG_SEPARATOR_NOTICE });
  });

  test("keeps a tag of exactly the maximum length", () => {
    const raw = "a".repeat(TAG_MAX_LENGTH);

    expect(sanitizeTagInput(raw)).toEqual({ value: raw, notice: null });
  });

  test("cuts a tag one character over the maximum length", () => {
    expect(sanitizeTagInput("a".repeat(TAG_MAX_LENGTH + 1))).toEqual({
      value: "a".repeat(TAG_MAX_LENGTH),
      notice: TAG_LENGTH_NOTICE,
    });
  });

  test("counts astral characters as one character", () => {
    const raw = "𝒜".repeat(TAG_MAX_LENGTH + 1);

    expect(Array.from(sanitizeTagInput(raw).value)).toHaveLength(TAG_MAX_LENGTH);
  });
});

describe("toTag", () => {
  test.each([
    ["c_", "c"],
    ["_a_b__", "a_b"],
    [" a ", "a"],
    ["__", ""],
  ])("turns '%s' into '%s'", (input, expected) => {
    expect(toTag(input)).toBe(expected);
  });
});
