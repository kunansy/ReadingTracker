export interface CursorStack<C> {
  /** `undefined` on the first page. */
  cursor: C | undefined;
  previous: readonly (C | undefined)[];
}

export const FIRST_PAGE: CursorStack<never> = { cursor: undefined, previous: [] };

export function pushCursor<C>(state: CursorStack<C>, nextCursor: C): CursorStack<C> {
  return { cursor: nextCursor, previous: [...state.previous, state.cursor] };
}

export function popCursor<C>(state: CursorStack<C>): CursorStack<C> {
  if (state.previous.length === 0) {
    return state;
  }
  return {
    cursor: state.previous[state.previous.length - 1],
    previous: state.previous.slice(0, -1),
  };
}

export type KeyedStack<C> = CursorStack<C> & { resetKey: string };

export function reconcileKey<C>(state: KeyedStack<C>, key: string): KeyedStack<C> {
  return state.resetKey === key ? state : { ...FIRST_PAGE, resetKey: key };
}
