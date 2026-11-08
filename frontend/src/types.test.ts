import { describe, expect, test } from "vitest";

import { isMaterialType, MaterialTypes } from "./types.ts";

describe("isMaterialType", () => {
  test.each(MaterialTypes)("accepts '%s'", (value) => {
    expect(isMaterialType(value)).toBe(true);
  });

  test.each(["", "podcast", "Book", " book"])("rejects '%s'", (value) => {
    expect(isMaterialType(value)).toBe(false);
  });
});
