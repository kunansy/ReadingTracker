import { describe, expect, test } from "vitest";

import { reverseOrder } from "./sortOrder.ts";

describe("reverseOrder", () => {
  test("flips asc and desc", () => {
    expect(reverseOrder("asc")).toBe("desc");
    expect(reverseOrder("desc")).toBe("asc");
  });
});
