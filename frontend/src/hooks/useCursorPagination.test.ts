// @vitest-environment jsdom
import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PageCursor, useCursorPagination } from "./useCursorPagination";
import type { SortOrder } from "./sortOrder";

const PAGE_SIZE = 10;

function render(resetKey = "", defaultOrder: SortOrder = "asc") {
  return renderHook(
    ({ key }) => useCursorPagination<PageCursor>(PAGE_SIZE, key, defaultOrder),
    { initialProps: { key: resetKey } },
  );
}

describe("useCursorPagination", () => {
  it("starts on the first page in the default order", () => {
    const { result } = render("", "desc");

    expect(result.current.cursor).toBeUndefined();
    expect(result.current.hasPrev).toBe(false);
    expect(result.current.offset).toBe(0);
    expect(result.current.order).toBe("desc");
  });

  it("goes forward and back through the visited pages", () => {
    const { result } = render();

    act(() => result.current.next({ nextToken: "a" }));
    act(() => result.current.next({ nextToken: "b" }));

    expect(result.current.cursor).toEqual({ nextToken: "b" });
    expect(result.current.hasPrev).toBe(true);
    expect(result.current.offset).toBe(2 * PAGE_SIZE);

    act(() => result.current.prev());

    expect(result.current.cursor).toEqual({ nextToken: "a" });
    expect(result.current.offset).toBe(PAGE_SIZE);

    act(() => result.current.prev());

    expect(result.current.cursor).toBeUndefined();
    expect(result.current.hasPrev).toBe(false);
  });

  it("returns to the first page when the reset key changes", () => {
    const { result, rerender } = render("material-1");

    act(() => result.current.next({ nextToken: "a" }));
    rerender({ key: "material-2" });

    expect(result.current.cursor).toBeUndefined();
    expect(result.current.hasPrev).toBe(false);
    expect(result.current.offset).toBe(0);
  });

  it("uses the new reset key for pages opened after the change", () => {
    const { result, rerender } = render("material-1");

    rerender({ key: "material-2" });
    act(() => result.current.next({ nextToken: "a" }));

    expect(result.current.cursor).toEqual({ nextToken: "a" });
    expect(result.current.hasPrev).toBe(true);
  });

  it("reverses the order and returns to the first page", () => {
    const { result } = render();

    act(() => result.current.next({ nextToken: "a" }));
    act(() => result.current.toggleOrder());

    expect(result.current.order).toBe("desc");
    expect(result.current.cursor).toBeUndefined();
    expect(result.current.hasPrev).toBe(false);
  });

  it("reset clears the visited pages", () => {
    const { result } = render();

    act(() => result.current.next({ nextToken: "a" }));
    act(() => result.current.next({ nextToken: "b" }));
    act(() => result.current.reset());

    expect(result.current.cursor).toBeUndefined();
    expect(result.current.hasPrev).toBe(false);
  });
});
