import { keepPreviousData, useQuery } from "@tanstack/react-query";
import {
    useCallback,
    useMemo,
    useEffect,
    useState,
} from "react";
import { useSearchParams } from "react-router-dom";

import { api, PAGE_SIZE, unwrap } from "../../api/client";
import { NotFoundMaterials } from "../../components/NotFoundMaterials";
import { PageNav } from "../../components/PageNav";
import { PageLoadError } from "../../components/PageLoadError";
import { useDebounce } from "../../lib/debounce.ts";
import { ScrollArrows } from "../../components/ScrollArrows";
import { useCursorPagination } from "../../hooks/useCursorPagination";
import { CompletedMaterialCard } from "./CompletedMaterialCard";
import { materialTypesEnumValues } from "../../api/schema";
import { isMaterialType } from "../../types";
import {
  ComboboxInput, ComboboxList, ComboboxRoot,
} from "../../components/Combobox";
import { materialKeys, useMaterialTags } from "../../materials/queries";

type OutlinedParam = "true" | "false" | "";

function readOutlinedParam(value: string | null): OutlinedParam {
  return value === "true" || value === "false" ? value : "";
}

export function ListCompletedMaterialsPage() {
  const [searchParams, setSearchParams] = useSearchParams();

  const [formState, setFormState] = useState({
    material_type: searchParams.get("material_type") ?? "",
    tags_query: searchParams.get("tags_query")
      ? searchParams.get("tags_query")!.split(" ")
      : [],
    is_outlined: readOutlinedParam(searchParams.get("is_outlined")),
  });

  useEffect(() => {
    setFormState({
      material_type: searchParams.get("material_type") ?? "",
      tags_query: searchParams.get("tags_query")
        ? searchParams.get("tags_query")!.split(" ")
        : [],
      is_outlined: readOutlinedParam(searchParams.get("is_outlined")),
      });
  }, [searchParams]);

  const debouncedForm = useDebounce(formState, 300);

  const filters = useMemo(() => ({
      material_type: isMaterialType(debouncedForm.material_type) ? debouncedForm.material_type : undefined,
      tags_query: debouncedForm.tags_query.length ? debouncedForm.tags_query.join(" ") : undefined,
      is_outlined: debouncedForm.is_outlined ? debouncedForm.is_outlined === "true" : undefined,
  }), [debouncedForm]);
  const filtersKey = JSON.stringify(filters);

  const pagination = useCursorPagination(PAGE_SIZE, filtersKey, "desc");
  const nextToken = pagination.cursor;

  const q = useQuery({
    queryKey: materialKeys.completedList(filtersKey, nextToken, pagination.order),
    placeholderData: keepPreviousData,
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/materials/completed", {
          params: {
            query: {
              ...filters,
              next_token: nextToken,
              page_size: PAGE_SIZE,
              order: pagination.order,
            },
          },
        }),
      ),
  });
  const materialTagsQ = useMaterialTags();

  const updateURL = useCallback(
      (state: typeof formState) => {
          const next: Record<string, string> = {};

          if (state.material_type) next.material_type = state.material_type;
          if (state.tags_query.length) {
              next.tags_query = state.tags_query.join(" ");
          }
          if (state.is_outlined) next.is_outlined = state.is_outlined;

          setSearchParams(next);
      },
      [setSearchParams]
  );

  const onSubmit = (e: React.FormEvent) => {
      e.preventDefault();
      updateURL(formState);
  };

  const handleOutlinedChange = (value: OutlinedParam) => {
      setFormState((prev) => ({ ...prev, is_outlined: value }));
  };

  if (q.isLoading || materialTagsQ.isLoading) return <p>Loading…</p>;

  if (materialTagsQ.error)
      return <p className="error">{materialTagsQ.error.message}</p>;

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
                      options={materialTypesEnumValues}
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
                              checked={formState.is_outlined === "true"}
                              onChange={() => handleOutlinedChange("true")}
                          />
                          Outlined only
                      </label>

                      <br />

                      <label>
                          <input
                              type="radio"
                              checked={formState.is_outlined === "false"}
                              onChange={() => handleOutlinedChange("false")}
                          />
                          Not outlined only
                      </label>

                      <br />

                      <label>
                          <input
                              type="radio"
                              checked={formState.is_outlined === ""}
                              onChange={() => handleOutlinedChange("")}
                          />
                          All
                      </label>
                  </div>

                  <button type="submit" className="submit-button">
                      Search
                  </button>
              </form>
          </div>

          {q.error ? (
              <PageLoadError pagination={pagination} error={q.error} />
          ) : (
              <>
                  <PageNav
                      pagination={pagination}
                      nextToken={q.data?.next_token}
                      isBusy={q.isPlaceholderData}
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
                      isBusy={q.isPlaceholderData}
                  />
              </>
          )}
        <ScrollArrows />
      </>
  );
}