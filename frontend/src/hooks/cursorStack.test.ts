import { describe, expect, test } from "vitest";

import {
  CursorStack,
  FIRST_PAGE,
  KeyedStack,
  popCursor,
  pushCursor,
  reconcileKey,
} from "./cursorStack.ts";

type QueueCursor = { nextToken: string; startDate: string };

const PAGE_2: QueueCursor = { nextToken: "token-2", startDate: "2025-02-01" };
const PAGE_3: QueueCursor = { nextToken: "token-3", startDate: "2025-03-01" };

describe("pushCursor", () => {
  test("opens the next page and remembers the first page as undefined", () => {
    const state = pushCursor<QueueCursor>(FIRST_PAGE, PAGE_2);

    expect(state).toEqual({ cursor: PAGE_2, previous: [undefined] });
  });

  test("stacks every visited cursor in order", () => {
    const state = pushCursor(pushCursor<QueueCursor>(FIRST_PAGE, PAGE_2), PAGE_3);

    expect(state).toEqual({ cursor: PAGE_3, previous: [undefined, PAGE_2] });
  });

  test("does not mutate the previous state", () => {
    const before: CursorStack<QueueCursor> = {
      cursor: PAGE_2,
      previous: [undefined],
    };

    pushCursor(before, PAGE_3);

    expect(before).toEqual({ cursor: PAGE_2, previous: [undefined] });
  });
});

describe("popCursor", () => {
  test("returns to the previously visited cursor", () => {
    const state = popCursor(pushCursor(pushCursor<QueueCursor>(FIRST_PAGE, PAGE_2), PAGE_3));

    expect(state).toEqual({ cursor: PAGE_2, previous: [undefined] });
  });

  test("returns to the first page with an undefined cursor", () => {
    const state = popCursor(pushCursor<QueueCursor>(FIRST_PAGE, PAGE_2));

    expect(state).toEqual(FIRST_PAGE);
  });

  test("keeps the first page unchanged", () => {
    expect(popCursor<QueueCursor>(FIRST_PAGE)).toBe(FIRST_PAGE);
  });
});

describe("reconcileKey", () => {
  test("keeps the same state object when the key matches", () => {
    const state: KeyedStack<QueueCursor> = {
      ...pushCursor<QueueCursor>(FIRST_PAGE, PAGE_2),
      resetKey: "a",
    };

    expect(reconcileKey(state, "a")).toBe(state);
  });

  test("drops the visited pages when the key changes", () => {
    const state: KeyedStack<QueueCursor> = {
      ...pushCursor<QueueCursor>(FIRST_PAGE, PAGE_2),
      resetKey: "a",
    };

    expect(reconcileKey(state, "b")).toEqual({ ...FIRST_PAGE, resetKey: "b" });
  });

  test("does not bring back old pages when the key returns to a previous value", () => {
    const onPage3: KeyedStack<QueueCursor> = {
      ...pushCursor(pushCursor<QueueCursor>(FIRST_PAGE, PAGE_2), PAGE_3),
      resetKey: "a",
    };

    const state = reconcileKey(reconcileKey(onPage3, "b"), "a");

    expect(state).toEqual({ ...FIRST_PAGE, resetKey: "a" });
  });
});
