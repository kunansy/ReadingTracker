import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useMemo, useEffect, useState } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";

import { apiFetch, buildQuery } from "../../api/materials";
import { CelebrateButton } from "../../components/CelebrateButton";
import { NotFoundMaterials } from "../../components/NotFoundMaterials";
import { useContextMenu } from "../../contexts/ContextMenuContext";
import { itemsLabel, itemsLabelLower } from "../../materials/format";
import {MaterialStatisticsJson, MaterialTagsResponse, MaterialTypes} from "../../types";

type CompletedResponse = {
  statistics: MaterialStatisticsJson[];
};

export function CompletedPage() {
  const qc = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const { open, close } = useContextMenu();
  const navigate = useNavigate();
  const [materialTags, setMaterialTags] = useState<MaterialTagsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void apiFetch<MaterialTagsResponse>("/tags").then(setMaterialTags).catch(() => {
      setError("Failed to load material tags");
    });
  }, []);

  const material_type = searchParams.get("material_type") ?? "";
  const tags_query = searchParams.get("tags_query") ?? "";
  const outlined = searchParams.get("outlined") ?? "all";

  const queryString = useMemo(() => {
    return buildQuery({
      material_type: material_type || undefined,
      tags_query: tags_query || undefined,
      outlined: outlined === "all" ? undefined : outlined,
    });
  }, [searchParams]);

  const q = useQuery({
    queryKey: ["materials", "completed", queryString],
    queryFn: () => apiFetch<CompletedResponse>(`/completed${queryString}`),
  });

  const outlineMut = useMutation({
    mutationFn: (materialId: string) =>
      apiFetch(`/${materialId}/outline`, { method: "POST" }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["materials"] });
    },
  });

  const onMaterialContextMenu = useCallback(
    (e: React.MouseEvent, materialId: string) => {
      e.preventDefault();
      close();
      open(e.clientX, e.clientY, [
        {
          label: "Edit",
          action: async () => {
            navigate(`/materials/update?material_id=${materialId}`);
          },
        },
        {
          label: "Open notes",
          action: async () => {
            navigate(`/notes?material_id=${materialId}`);
          },
        },
        {
          label: "Add note",
          action: async () => {
            navigate(`/notes/add?material_id=${materialId}`);
          },
        },
      ]);
    },
    [close, open],
  );

  const onSearchSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const material_type = String(fd.get("material_type") ?? "");
    const tags_query = String(fd.get("tags_query") ?? "");
    const outlined = String(fd.get("outlined") ?? "all");
    const next: Record<string, string> = {};
    if (material_type) {
      next.material_type = material_type;
    }
    if (tags_query) {
      next.tags_query = tags_query;
    }
    if (outlined && outlined !== "all") {
      next.outlined = outlined;
    }
    setSearchParams(next);
  };

  if (q.isLoading) {
    return <p>Loading…</p>;
  }
  if (q.error) {
    return <p className="error">{(q.error as Error).message}</p>;
  }

  const stats = q.data?.statistics ?? [];

  return (
    <>
      {error ? <div className="alert error">{error}</div> : null}
      <form id="search-materials-form" onSubmit={onSearchSubmit}>
        <input
          className="input"
          list="material_types"
          name="material_type"
          value={material_type}
          onChange={(e) =>
              setSearchParams((prev) => {
                const next = new URLSearchParams(prev);
                if (e.target.value) {
                  next.set("material_type", e.target.value);
                } else {
                  next.delete("material_type");
                }
                return next;
              })
          }
          placeholder="Choose a material type"
        />
        <input
          className="input"
          list="tags"
          name="tags_query"
          value={tags_query}
          onChange={(e) =>
              setSearchParams((prev) => {
                const next = new URLSearchParams(prev);
                if (e.target.value) {
                  next.set("tags_query", e.target.value);
                } else {
                  next.delete("tags_query");
                }
                return next;
              })
          }
          placeholder="Choose material tags"
        />
        <div className="outlined-checkbox">
          <input
            type="radio"
            id="outlined"
            name="outlined"
            value="outlined"
            checked={outlined === "outlined"}
            onChange={(e) =>
                setSearchParams((prev) => {
                  const next = new URLSearchParams(prev);
                  next.set("outlined", e.target.value);
                  return next;
                })
            }
          />
          <label htmlFor="outlined"> Outlined only </label>
          <br />
          <input
            type="radio"
            id="not_outlined"
            name="outlined"
            value="not_outlined"
            checked={outlined === "not_outlined"}
            onChange={(e) =>
                setSearchParams((prev) => {
                  const next = new URLSearchParams(prev);
                  next.set("outlined", e.target.value);
                  return next;
                })
            }
          />
          <label htmlFor="not_outlined"> Not outlined only </label>
          <br />
          <input
            type="radio"
            id="all"
            name="outlined"
            value="all"
            checked={outlined === "all"}
            onChange={(_) =>
                setSearchParams((prev) => {
                  const next = new URLSearchParams(prev);
                  next.delete("outlined");
                  return next;                })
            }
          />
          <label htmlFor="all"> All </label>
        </div>
        <datalist id="tags">
          {(materialTags?.tagsList ?? []).map((tag) => (
            <option key={tag} value={tag}>
              #{tag}
            </option>
          ))}
        </datalist>
        <datalist id="material_types">
          {(MaterialTypes ?? []).map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </datalist>
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
            const isOutlined = material.is_outlined ? "Yes" : "No";
            return (
              <div
                key={material.material_id}
                className="material hover"
                id={material.material_id}
                onContextMenu={(e) =>
                  onMaterialContextMenu(e, material.material_id)
                }
              >
                <p className="little-text">
                  {idx + 1} / {stats.length}
                </p>
                <p> Title: «{material.title}» </p>
                <p> Author: {material.authors} </p>
                <p>
                  {il}: {material.pages}
                </p>
                <p> Type: {material.material_type} </p>
                {material.tags ? <p> Tags: {material.tags} </p> : null}
                {material.link ? <p> Link: {material.link} </p> : null}
                <p> Is outlined: {isOutlined} </p>
                <hr title="Analytics" />
                <p> Started at: {ms.started_at} </p>
                <p> Completed at: {ms.completed_at} </p>
                <p> Total duration: {ms.total_reading_duration} </p>
                <p> Notes count: {ms.notes_count} notes </p>
                <p> Was being reading: {ms.duration} days </p>
                <p> Lost time: {ms.lost_time} days </p>
                <p>
                  Mean: {ms.mean} {ill} per day
                </p>
                {ms.max_record && ms.min_record ? (
                  <>
                    <hr title="Min/max" />
                    <p>
                      Max: {ms.max_record.count} {ill}, {ms.max_record.date}
                    </p>
                    <p>
                      Min: {ms.min_record.count} {ill}, {ms.min_record.date}
                    </p>
                  </>
                ) : null}
                {!material.is_outlined ? (
                  <form
                    className="outline"
                    title={`Mark the material id=${material.material_id} as outlined`}
                    onSubmit={(e) => {
                      e.preventDefault();
                      outlineMut.mutate(material.material_id);
                    }}
                  >
                    <CelebrateButton type="submit" className="submit-button">
                      Outline
                    </CelebrateButton>
                  </form>
                ) : null}
              </div>
            );
          })
      )}
      {error ? <p className="error">{error}</p> : null}
    </>
  );
}
