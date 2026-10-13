import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { dateInputValue } from "./dateInputValue.ts";

describe("dateInputValue", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  test("formats today with zero-padded month and day", () => {
    vi.setSystemTime(new Date(2025, 2, 5, 12));

    expect(dateInputValue()).toBe("2025-03-05");
  });

  test("returns the previous day when daysAgo is 1", () => {
    vi.setSystemTime(new Date(2025, 10, 20, 12));

    expect(dateInputValue(1)).toBe("2025-11-19");
  });

  test("crosses a month boundary into a leap day", () => {
    vi.setSystemTime(new Date(2024, 2, 1, 12));

    expect(dateInputValue(1)).toBe("2024-02-29");
  });

  test("crosses a year boundary", () => {
    vi.setSystemTime(new Date(2025, 0, 1, 12));

    expect(dateInputValue(1)).toBe("2024-12-31");
  });

  test("uses the local calendar day just after midnight", () => {
    vi.setSystemTime(new Date(2025, 5, 10, 0, 5));

    expect(dateInputValue()).toBe("2025-06-10");
  });
});
