import type { ReactNode } from "react";
import type { UseQueryResult } from "@tanstack/react-query";

type QueryStateProps<TData, TError = unknown> = {
  data: TData | undefined;
  isLoading: boolean;
  isError: boolean;
  error: TError;
  children: (data: TData) => ReactNode;
  loading?: ReactNode;
  errorRenderer?: (error: TError) => ReactNode;
  empty?: ReactNode;
};

export function QueryState<TData, TError = unknown>({
  data,
  isLoading,
  isError,
  error,
  children,
  loading = <p>Loading…</p>,
  errorRenderer = (err) => <p className="error">{String(err)}</p>,
  empty = null,
}: QueryStateProps<TData, TError>) {
  if (isLoading) return <>{loading}</>;
  if (isError) return <>{errorRenderer(error)}</>;
  if (data === undefined) return <>{empty}</>;
  return <>{children(data)}</>;
}

type QueryStateFromResultProps<TData, TError = unknown> = {
  query: UseQueryResult<TData, TError>;
  children: (data: TData) => ReactNode;
  loading?: ReactNode;
  errorRenderer?: (error: TError) => ReactNode;
  empty?: ReactNode;
};

// TODO: refactor pages with this component
export function QueryStateFromResult<TData, TError = unknown>({
  query,
  children,
  loading = <p>Loading…</p>,
  errorRenderer = (err) => <p className="error">{String(err)}</p>,
  empty = null,
}: QueryStateFromResultProps<TData, TError>) {
  if (query.isLoading) return <>{loading}</>;
  if (query.isError) return <>{errorRenderer(query.error)}</>;
  if (query.data === undefined) return <>{empty}</>;
  return <>{children(query.data)}</>;
}