import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { api, unwrap } from "../../api/client";
import { CelebrateButton } from "../../components/CelebrateButton";
import { useContextMenu } from "../../contexts/ContextMenuContext";
import { itemsLabel, itemsLabelLower } from "../../materials/format";
import type { MaterialStatistics } from "../../api/schema";

interface CompletedMaterialCardProps {
  stats: MaterialStatistics;
  /** 1-based position in the whole list, shown as "position / total". */
  position?: { index: number; total: number };
}

export function CompletedMaterialCard({ stats: ms, position }: CompletedMaterialCardProps) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const location = useLocation();
  const { open, close } = useContextMenu();

  const outlineMut = useMutation({
    mutationFn: (materialId: string) =>
      unwrap(
        api.POST("/api/v1/materials/{material_id}/outline", {
          params: { path: { material_id: materialId } },
        }),
      ),
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
          action: async () =>
            navigate(`/materials/update?material_id=${materialId}`, {
              state: { from: location.pathname + location.search },
            }),
        },
        {
          label: "Open notes",
          action: async () => navigate(`/notes?material_id=${materialId}`),
        },
        {
          label: "Add note",
          action: async () => navigate(`/notes/add?material_id=${materialId}`),
        },
      ]);
    },
    [close, open, navigate, location.pathname, location.search],
  );

  const material = ms.material;
  const il = itemsLabel(material.material_type);
  const ill = itemsLabelLower(material.material_type);

  return (
    <div
      id={material.material_id}
      className="material hover"
      onContextMenu={(e) => onMaterialContextMenu(e, material.material_id)}
    >
      {position && (
        <p className="little-text">
          {position.index} / {position.total}
        </p>
      )}
      <p>Title: «{material.title}»</p>
      <p>Author: {material.authors}</p>
      <p>
        {il}: {material.pages}
      </p>
      <p>Type: {material.material_type}</p>
      {material.tags && <p>Tags: {material.tags}</p>}
      {material.link && <p>Link: {material.link}</p>}
      <p>Is outlined: {material.is_outlined ? "Yes" : "No"}</p>

      <hr title="Analytics" />

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
            Max: {ms.max_record.count} {ill}, {ms.max_record.date}
          </p>
          <p>
            Min: {ms.min_record.count} {ill}, {ms.min_record.date}
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
          <CelebrateButton type="submit" className="submit-button">
            Outline
          </CelebrateButton>
        </form>
      )}
    </div>
  );
}
