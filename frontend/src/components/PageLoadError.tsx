import { PageNav, type PageNavPagination } from "./PageNav";

interface PageLoadErrorProps {
  pagination: PageNavPagination;
  error: unknown;
}

/** Shows the error in place of a page and keeps Prev, so a failed page is not a dead end. */
export function PageLoadError({ pagination, error }: PageLoadErrorProps) {
  const message = error instanceof Error ? error.message : String(error);
  return (
    <>
      <p className="error" role="alert">
        {message}
      </p>
      <PageNav pagination={pagination} nextToken={null} />
    </>
  );
}
