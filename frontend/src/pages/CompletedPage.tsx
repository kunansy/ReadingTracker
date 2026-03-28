import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";

import { apiFetch, buildQuery } from "../api";
import { CelebrateButton } from "../components/CelebrateButton";
import { NotFoundMaterials } from "../components/NotFoundMaterials";
import { useContextMenu } from "../contexts/ContextMenuContext";
import { itemsLabel, itemsLabelLower } from "../materials/format";
import type { MaterialStatisticsJson } from "../types";

type CompletedResponse = {
  statistics: MaterialStatisticsJson[];
  tags: string[];
  material_types: string[];
  material_type: string | null;
  tags_query: string | null;
  outlined: string | null;
};

export function CompletedPage() {
  const qc = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const { open, close } = useContextMenu();

  const queryString = useMemo(() => {
    const material_type = searchParams.get("material_type") ?? "";
    const tags_query = searchParams.get("tags_query") ?? "";
    const outlined = searchParams.get("outlined") ?? "all";
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
            window.open(`/materials/update-view?material_id=${materialId}`);
          },
        },
        {
          label: "Open notes",
          action: async () => {
            window.open(`/notes?material_id=${materialId}`);
          },
        },
        {
          label: "Add note",
          action: async () => {
            window.open(`/notes/add-view?material_id=${materialId}`);
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

  const data = q.data;
  const stats = data?.statistics ?? [];

  return (
    <>
      <form id="search-materials-form" onSubmit={onSearchSubmit}>
        <input
          className="input"
          list="material_types"
          name="material_type"
          defaultValue={data?.material_type ?? ""}
          placeholder="Choose a material type"
        />
        <input
          className="input"
          list="tags"
          name="tags_query"
          defaultValue={data?.tags_query ?? ""}
          placeholder="Choose material tags"
        />
        <div className="outlined-checkbox">
          <input
            type="radio"
            id="outlined"
            name="outlined"
            value="outlined"
            defaultChecked={data?.outlined === "outlined"}
          />
          <label htmlFor="outlined"> Outlined only </label>
          <br />
          <input
            type="radio"
            id="not_outlined"
            name="outlined"
            value="not_outlined"
            defaultChecked={data?.outlined === "not_outlined"}
          />
          <label htmlFor="not_outlined"> Not outlined only </label>
          <br />
          <input
            type="radio"
            id="all"
            name="outlined"
            value="all"
            defaultChecked={!data?.outlined || data.outlined === "all"}
          />
          <label htmlFor="all"> All </label>
        </div>
        <datalist id="tags">
          {(data?.tags ?? []).map((tag) => (
            <option key={tag} value={tag}>
              #{tag}
            </option>
          ))}
        </datalist>
        <datalist id="material_types">
          {(data?.material_types ?? []).map((t) => (
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
    </>
  );
}
