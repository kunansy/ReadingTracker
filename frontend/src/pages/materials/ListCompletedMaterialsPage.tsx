import { useQuery } from "@tanstack/react-query";
import {
    useCallback,
    useMemo,
    useEffect,
    useState,
} from "react";
import { useSearchParams } from "react-router-dom";

import { apiFetch, buildQuery, PAGE_SIZE } from "../../api/materials";
import { NotFoundMaterials } from "../../components/NotFoundMaterials";
import { PageNav } from "../../components/PageNav";
import { useDebounce } from "../../lib/debounce.ts";
import { ScrollArrows } from "../../components/ScrollArrows";
import { PageCursor, useCursorPagination } from "../../hooks/useCursorPagination";
import { CompletedMaterialCard } from "./CompletedMaterialCard";
import {
    ListCompletedMaterialsResponse,
    MaterialTagsResponse,
    MaterialTypes,
} from "../../types";
import {
  ComboboxInput, ComboboxList, ComboboxRoot,
} from "../../components/Combobox";


export function ListCompletedMaterialsPage() {
  const [searchParams, setSearchParams] = useSearchParams();

  const [formState, setFormState] = useState({
    material_type: searchParams.get("material_type") ?? "",
    tags_query: searchParams.get("tags_query")
      ? searchParams.get("tags_query")!.split(" ")
      : [],
    outlined: searchParams.get("outlined") ?? "all",
  });

  useEffect(() => {
    setFormState({
      material_type: searchParams.get("material_type") ?? "",
      tags_query: searchParams.get("tags_query")
        ? searchParams.get("tags_query")!.split(" ")
        : [],
      outlined: searchParams.get("outlined") ?? "all",
      });
  }, [searchParams]);

  const debouncedForm = useDebounce(formState, 300);

  const filters = useMemo(() => ({
      material_type: debouncedForm.material_type || undefined,
      tags_query: debouncedForm.tags_query.length ? debouncedForm.tags_query.join(" ") : undefined,
      outlined: debouncedForm.outlined === "all" ? undefined : debouncedForm.outlined,
  }), [debouncedForm]);
  const filtersQuery = buildQuery(filters);

  const pagination = useCursorPagination<PageCursor>(PAGE_SIZE, filtersQuery, "desc");
  const nextToken = pagination.cursor?.nextToken;

  const q = useQuery({
    queryKey: ["materials", "completed", "list", filtersQuery, nextToken, pagination.order],
    queryFn: () =>
      apiFetch<ListCompletedMaterialsResponse>(
        `/completed${buildQuery({ ...filters, next_token: nextToken, page_size: PAGE_SIZE, order: pagination.order })}`,
      ),
  });
  const materialTagsQ = useQuery({
    queryKey: ["materials", "tags"],
    queryFn: () => apiFetch<MaterialTagsResponse>(`/tags`),
    staleTime: 5 * 60 * 1000,
  });

  const updateURL = useCallback(
      (state: typeof formState) => {
          const next: Record<string, string> = {};

          if (state.material_type) next.material_type = state.material_type;
          if (state.tags_query.length) {
              next.tags_query = state.tags_query.join(" ");
          }
          if (state.outlined && state.outlined !== "all") {
              next.outlined = state.outlined;
          }

          setSearchParams(next);
      },
      [setSearchParams]
  );

  const onSubmit = (e: React.FormEvent) => {
      e.preventDefault();
      updateURL(formState);
  };

  const handleOutlinedChange = (value: string) => {
      setFormState((prev) => ({ ...prev, outlined: value }));
  };

  if (q.isLoading || materialTagsQ.isLoading) return <p>Loading…</p>;

  const err = q.error || materialTagsQ.error;
  if (err)
      return <p className="error">{(err as Error).message}</p>;

  const stats = q.data?.statistics ?? [];
  const materialTags = materialTagsQ.data?.tags ?? [];

  return (
      <>
          <div className="form">
              <form onSubmit={onSubmit}>
                  <ComboboxRoot
                      value={formState.material_type}
                      onChange={(v) =>
                          setFormState((p) => ({ ...p, material_type: v }))
                      }
                      options={MaterialTypes ?? []}
                  >
                      <ComboboxInput placeholder="Enter a material type" />
                      <ComboboxList />
                  </ComboboxRoot>

                  <ComboboxRoot
                      value={formState.tags_query}
                      onChange={(v) =>
                          setFormState((p) => ({ ...p, tags_query: v }))
                      }
                      options={materialTags}
                      multiple
                      allowCreate
                  >
                      <ComboboxInput placeholder="Enter material tags" />
                      <ComboboxList />
                  </ComboboxRoot>

                  <div className="outlined-checkbox">
                      <label>
                          <input
                              type="radio"
                              checked={formState.outlined === "outlined"}
                              onChange={() => handleOutlinedChange("outlined")}
                          />
                          Outlined only
                      </label>

                      <br />

                      <label>
                          <input
                              type="radio"
                              checked={formState.outlined === "not_outlined"}
                              onChange={() => handleOutlinedChange("not_outlined")}
                          />
                          Not outlined only
                      </label>

                      <br />

                      <label>
                          <input
                              type="radio"
                              checked={formState.outlined === "all"}
                              onChange={() => handleOutlinedChange("all")}
                          />
                          All
                      </label>
                  </div>

                  <button type="submit" className="submit-button">
                      Search
                  </button>
              </form>
          </div>

          <PageNav
              pagination={pagination}
              nextToken={q.data?.next_token}
              onNext={(token) => pagination.next({ nextToken: token })}
          />
          {!stats.length ? (
              <NotFoundMaterials kind="completed materials" />
          ) : (
              stats.map((ms, idx) => (
                  <CompletedMaterialCard
                      key={ms.material.material_id}
                      stats={ms}
                      position={{ index: pagination.offset + idx + 1, total: q.data?.total_count ?? 0 }}
                  />
              ))
          )}
          <PageNav
              pagination={pagination}
              nextToken={q.data?.next_token}
              onNext={(token) => pagination.next({ nextToken: token })}
          />
        <ScrollArrows />
      </>
  );
}