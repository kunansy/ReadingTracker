import { useCallback, useState } from "react";

import { FIRST_PAGE, KeyedStack, popCursor, pushCursor, reconcileKey } from "./cursorStack.ts";
import { reverseOrder, SortOrder } from "./sortOrder.ts";

export type PageCursor = { nextToken: string };

export interface CursorPagination<C> {
  /** `undefined` on the first page. */
  cursor: C | undefined;
  next: (nextCursor: C) => void;
  prev: () => void;
  reset: () => void;
  hasPrev: boolean;
  offset: number;
  order: SortOrder;
  toggleOrder: () => void;
}

/**
 * Keeps the cursor of the current page and the cursors of the pages visited before it.
 * A change of `resetKey` (e.g. serialized filters) or of the order brings the pagination
 * back to the first page.
 */
export function useCursorPagination<C>(
  pageSize: number,
  resetKey = "",
  defaultOrder: SortOrder = "asc",
): CursorPagination<C> {
  const [order, setOrder] = useState<SortOrder>(defaultOrder);
  const key = `${resetKey}\u0000${order}`;
  const [state, setState] = useState<KeyedStack<C>>({
    ...FIRST_PAGE,
    resetKey: key,
  });

  const current = reconcileKey(state, key);
  if (current !== state) {
    setState(current);
  }

  const next = useCallback(
    (nextCursor: C) => {
      setState((prev) => ({
        ...pushCursor(reconcileKey(prev, key), nextCursor),
        resetKey: key,
      }));
    },
    [key],
  );

  const prev = useCallback(() => {
    setState((prevState) => ({
      ...popCursor(reconcileKey(prevState, key)),
      resetKey: key,
    }));
  }, [key]);

  const reset = useCallback(() => {
    setState({ ...FIRST_PAGE, resetKey: key });
  }, [key]);

  const toggleOrder = useCallback(() => {
    setOrder(reverseOrder);
  }, []);

  return {
    cursor: current.cursor,
    next,
    prev,
    reset,
    hasPrev: current.previous.length > 0,
    offset: current.previous.length * pageSize,
    order,
    toggleOrder,
  };
}
