import type { SortOrder } from "../hooks/sortOrder";

export interface PageNavPagination {
  hasPrev: boolean;
  next: (nextToken: string) => void;
  prev: () => void;
  order: SortOrder;
  toggleOrder: () => void;
}

interface PageNavProps {
  pagination: PageNavPagination;
  /** `next_token` of the current response; `null` means there are no more pages. */
  nextToken: string | null | undefined;
  /**
   * The shown page is a placeholder while the requested one loads, so its token is stale.
   * Buttons ignore clicks via `aria-disabled` instead of `disabled` to keep keyboard focus.
   */
  isBusy?: boolean;
}

const ORDER_LABELS: Record<SortOrder, string> = {
  asc: "↑ Asc",
  desc: "↓ Desc",
};

export function PageNav({ pagination, nextToken, isBusy = false }: PageNavProps) {
  const { hasPrev, next, prev, order, toggleOrder } = pagination;
  const hasPages = hasPrev || Boolean(nextToken);
  const unlessBusy = (action: () => void) => () => {
    if (!isBusy) action();
  };

  return (
    <nav
      className="form hints"
      aria-label="Pagination"
      aria-busy={isBusy}
      style={{ justifyContent: "center", margin: "2vh auto" }}
    >
      {hasPages && (
        <button
          type="button"
          className="hint-button"
          disabled={!hasPrev}
          aria-disabled={isBusy}
          onClick={unlessBusy(prev)}
        >
          « Prev
        </button>
      )}
      <button
        type="button"
        className="hint-button"
        title="Reverse the order"
        aria-label={`Order: ${order}, reverse`}
        aria-disabled={isBusy}
        onClick={unlessBusy(toggleOrder)}
      >
        {ORDER_LABELS[order]}
      </button>
      {hasPages && (
        <button
          type="button"
          className="hint-button"
          disabled={!nextToken}
          aria-disabled={isBusy}
          onClick={unlessBusy(() => {
            if (nextToken) next(nextToken);
          })}
        >
          Next »
        </button>
      )}
    </nav>
  );
}
