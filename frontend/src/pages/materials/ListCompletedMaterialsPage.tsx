import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
    useCallback,
    useMemo,
    useEffect,
    useState,
    useRef,
} from "react";
import {useSearchParams, useNavigate, useLocation} from "react-router-dom";

import { apiFetch, buildQuery } from "../../api/materials";
import { CelebrateButton } from "../../components/CelebrateButton";
import { NotFoundMaterials } from "../../components/NotFoundMaterials";
import { useContextMenu } from "../../contexts/ContextMenuContext";
import { useDebounce } from "../../lib/debounce.ts";
import { itemsLabel, itemsLabelLower } from "../../materials/format";
import {
    ListCompletedMaterialsResponse,
    MaterialTagsResponse,
    MaterialTypes,
} from "../../types";
import {
  ComboboxInput, ComboboxList, ComboboxRoot,
} from "../../components/Combobox";


export function ListCompletedMaterialsPage() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { open, close } = useContextMenu();
  const location = useLocation();
  const [didScroll, setDidScroll] = useState(false);
  const refs = useRef<Record<string, HTMLDivElement | null>>({});

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

  const queryString = useMemo(() => {
    return buildQuery({
      material_type: debouncedForm.material_type || undefined,
      tags_query: debouncedForm.tags_query.length ? debouncedForm.tags_query.join(" ") : undefined,
      outlined: debouncedForm.outlined === "all" ? undefined : debouncedForm.outlined,
    });
  }, [debouncedForm]);

  const q = useQuery({
    queryKey: ["materials", "completed", queryString],
    queryFn: () =>
      apiFetch<ListCompletedMaterialsResponse>(`/completed${queryString}`),
  });
  const materialTagsQ = useQuery({
    queryKey: ["materials", "tags"],
    queryFn: () => apiFetch<MaterialTagsResponse>(`/tags`),
    staleTime: 5 * 60 * 1000,
  });

  const outlineMut = useMutation({
      mutationFn: (materialId: string) =>
          apiFetch(`/${materialId}/outline`, { method: "POST" }),
      onSuccess: () => {
          void qc.invalidateQueries({ queryKey: ["materials"] });
      },
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

  const onMaterialContextMenu = useCallback(
      (e: React.MouseEvent, materialId: string) => {
          e.preventDefault();
          close();
          open(e.clientX, e.clientY, [
              {
                  label: "Edit",
                  action: async () =>
                      navigate(`/materials/update?material_id=${materialId}`, {
                          state: { from: location.pathname + location.search },
                      })
              },
              {
                  label: "Open notes",
                  action: async () =>
                      navigate(`/notes?material_id=${materialId}`),
              },
              {
                  label: "Add note",
                  action: async () =>
                      navigate(`/notes/add?material_id=${materialId}`),
              },
          ]);
      },
      [close, open, navigate]
  );

  const handleOutlinedChange = (value: string) => {
      setFormState((prev) => ({ ...prev, outlined: value }));
  };

    useEffect(() => {
        const id = location.state?.scrollTo;
        if (!id) return;

        if (!q.data) return;

        if (didScroll) return;

        const el = refs.current[id];
        if (el) {
            el.scrollIntoView({
                behavior: "smooth",
                block: "center",
            });

            setDidScroll(true);
        }
    }, [location.state, q.data, didScroll]);

    useEffect(() => {
        if (didScroll) {
            navigate(location.pathname + location.search, { replace: true });
        }
    }, [didScroll]);

  if (q.isLoading || materialTagsQ.isLoading) return <p>Loading…</p>;

  const err = q.error || materialTagsQ.error;
  if (err)
      return <p className="error">{(err as Error).message}</p>;

  const stats = q.data?.statistics ?? [];
  const materialTags = materialTagsQ.data?.tags ?? [];

  return (
      <>
          <form id="search-materials-form" onSubmit={onSubmit}>
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

          {!stats.length ? (
              <NotFoundMaterials kind="completed materials" />
          ) : (
              [...stats]
                  .sort((a, b) => {
                      const ac = a.completed_at ?? a.material.added_at;
                      const bc = b.completed_at ?? b.material.added_at;
                      return String(ac).localeCompare(String(bc));
                  })
                  .map((ms, idx) => {
                      const material = ms.material;
                      const il = itemsLabel(material.material_type);
                      const ill = itemsLabelLower(material.material_type);

                      return (
                          <div
                              key={material.material_id}
                              id={material.material_id}
                              ref={(el) => {
                                  refs.current[material.material_id] = el;
                              }}
                              className="material hover"
                              onContextMenu={(e) =>
                                  onMaterialContextMenu(e, material.material_id)
                              }
                          >
                              <p className="little-text">
                                  {idx + 1} / {stats.length}
                              </p>
                              <p>Title: «{material.title}»</p>
                              <p>Author: {material.authors}</p>
                              <p>
                                  {il}: {material.pages}
                              </p>
                              <p>Type: {material.material_type}</p>
                              {material.tags && <p>Tags: {material.tags}</p>}
                              {material.link && <p>Link: {material.link}</p>}
                              <p>
                                  Is outlined: {material.is_outlined ? "Yes" : "No"}
                              </p>

                              <hr title="Analytics"/>

                              <p>Started at: {ms.started_at}</p>
                              <p>Completed at: {ms.completed_at}</p>
                              <p>Total duration: {ms.total_reading_duration}</p>
                              <p>Notes count: {ms.notes_count}</p>
                              <p>Was being reading: {ms.duration} days</p>
                              <p>Lost time: {ms.lost_time} days</p>
                              <p>
                                  Mean: {ms.mean} {ill} per day
                              </p>

                              {ms.max_record && ms.min_record && (
                                  <>
                                      <hr title="Min/max" />
                                      <p>
                                          Max: {ms.max_record.count} {ill},{" "}
                                          {ms.max_record.date}
                                      </p>
                                      <p>
                                          Min: {ms.min_record.count} {ill},{" "}
                                          {ms.min_record.date}
                                      </p>
                                  </>
                              )}

                              {!material.is_outlined && (
                                  <form
                                      className="outline"
                                      title={`Mark the material id=${material.material_id} as outlined`}
                                      onSubmit={(e) => {
                                          e.preventDefault();
                                          outlineMut.mutate(material.material_id);
                                      }}
                                  >
                                      <CelebrateButton
                                          type="submit"
                                          className="submit-button">
                                          Outline
                                      </CelebrateButton>
                                  </form>
                              )}
                          </div>
                      );
                  })
          )}
      </>
  );
}