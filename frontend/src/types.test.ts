import { describe, expect, test } from "vitest";

import { materialTypesEnumValues } from "./api/schema";
import { isMaterialType } from "./types.ts";

describe("isMaterialType", () => {
  test.each(materialTypesEnumValues)("accepts '%s'", (value) => {
    expect(isMaterialType(value)).toBe(true);
  });

  test.each(["", "podcast", "Book", " book"])("rejects '%s'", (value) => {
    expect(isMaterialType(value)).toBe(false);
  });
});
