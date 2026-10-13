import { describe, expect, test } from "vitest";

import { isMaterialType, MaterialType } from "./types.ts";

describe("isMaterialType", () => {
  test.each(Object.values(MaterialType))("accepts '%s'", (value) => {
    expect(isMaterialType(value)).toBe(true);
  });

  test.each(["", "podcast", "Book", " book"])("rejects '%s'", (value) => {
    expect(isMaterialType(value)).toBe(false);
  });
});
