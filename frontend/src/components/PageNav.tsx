import type { SortOrder } from "../hooks/sortOrder";

interface PageNavPagination {
  hasPrev: boolean;
  prev: () => void;
  order: SortOrder;
  toggleOrder: () => void;
}

interface PageNavProps {
  pagination: PageNavPagination;
  /** `next_token` of the current response; `null` means there are no more pages. */
  nextToken: string | null | undefined;
  onNext: (nextToken: string) => void;
}

const ORDER_LABELS: Record<SortOrder, string> = {
  asc: "↑ Asc",
  desc: "↓ Desc",
};

export function PageNav({ pagination, nextToken, onNext }: PageNavProps) {
  const { hasPrev, prev, order, toggleOrder } = pagination;
  const hasPages = hasPrev || Boolean(nextToken);

  return (
    <nav
      className="form hints"
      aria-label="Pagination"
      style={{ justifyContent: "center", margin: "2vh auto" }}
    >
      {hasPages && (
        <button type="button" className="hint-button" disabled={!hasPrev} onClick={prev}>
          « Prev
        </button>
      )}
      <button
        type="button"
        className="hint-button"
        title="Reverse the order"
        aria-label={`Order: ${order}, reverse`}
        onClick={toggleOrder}
      >
        {ORDER_LABELS[order]}
      </button>
      {hasPages && (
        <button
          type="button"
          className="hint-button"
          disabled={!nextToken}
          onClick={() => {
            if (nextToken) onNext(nextToken);
          }}
        >
          Next »
        </button>
      )}
    </nav>
  );
}
