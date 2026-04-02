import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";

import { apiFetch } from "@/api/materials.ts";
import { NotFoundMaterials } from "../../components/NotFoundMaterials";
import { useContextMenu } from "../../contexts/ContextMenuContext";
import { itemsLabel, itemsLabelLower } from "@/materials/format.ts";
import type { MaterialEstimateJson } from "@/types.ts";

type QueueResponse = {
  estimates: MaterialEstimateJson[];
  mean: Record<string, number>;
};

export function QueuePage() {
  const qc = useQueryClient();
  const { open, close } = useContextMenu();

  const q = useQuery({
    queryKey: ["materials", "queue"],
    queryFn: () => apiFetch<QueueResponse>("/queue"),
  });

  const startMut = useMutation({
    mutationFn: (materialId: string) =>
      apiFetch(`/${materialId}/start`, { method: "POST" }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["materials"] });
    },
  });

  const swapMut = useMutation({
    mutationFn: (p: { material_id: string; index: number }) =>
      apiFetch("/queue/swap-order", {
        method: "POST",
        body: JSON.stringify(p),
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["materials"] });
    },
  });

  const onQueueContextMenu = useCallback(
    async (e: React.MouseEvent, materialId: string, index: number) => {
      e.preventDefault();
      close();
      const [start, end] = await Promise.all([
        apiFetch<{ index: number }>("/queue/start"),
        apiFetch<{ index: number }>("/queue/end"),
      ]);
      if (!start || !end) {
        return;
      }
      const queueStart = start.index;
      const queueEnd = end.index;
      const items: { label: string; action: () => Promise<void> }[] = [
        {
          label: "Edit",
          action: async () => {
            window.open(`/materials/update-view?material_id=${materialId}`);
          },
        },
      ];
      if (index > queueStart) {
        items.push({
          label: "Move top",
          action: async () => {
            await swapMut.mutateAsync({
              material_id: materialId,
              index: queueStart,
            });
          },
        });
        items.push({
          label: "Move upper",
          action: async () => {
            await swapMut.mutateAsync({
              material_id: materialId,
              index: index - 1,
            });
          },
        });
      }
      if (index < queueEnd) {
        items.push({
          label: "Move lower",
          action: async () => {
            await swapMut.mutateAsync({
              material_id: materialId,
              index: index + 1,
            });
          },
        });
        items.push({
          label: "Move bottom",
          action: async () => {
            await swapMut.mutateAsync({
              material_id: materialId,
              index: queueEnd,
            });
          },
        });
      }
      open(e.clientX, e.clientY, items);
    },
    [close, open, swapMut],
  );

  if (q.isLoading) {
    return <p>Loading…</p>;
  }
  if (q.error) {
    return <p className="error">{(q.error as Error).message}</p>;
  }
  const data = q.data;
  if (!data?.estimates?.length) {
    return <NotFoundMaterials kind="materials" />;
  }

  return (
    <>
      {data.estimates.map((estimate, i) => {
        const material = estimate.material;
        const il = itemsLabel(material.material_type);
        const ill = itemsLabelLower(material.material_type);
        const mean = data.mean[material.material_type] ?? 1;
        return (
          <div
            key={material.material_id}
            className="material hover queue-item"
            id={material.material_id}
            data-index={String(material.index)}
            onContextMenu={(e) =>
              void onQueueContextMenu(e, material.material_id, material.index)
            }
          >
            <p className="little-text">
              {" "}
              {i + 1} / {data.estimates.length}
            </p>
            <p> Title: «{material.title}» </p>
            <p> Author: {material.authors} </p>
            <p>
              {" "}
              {il}: {material.pages}{" "}
            </p>
            <p> Type: {material.material_type} </p>
            {material.tags ? <p> Tags: {material.tags} </p> : null}
            {material.link ? <p> Link: {material.link} </p> : null}
            <hr />
            <p> Will be started: {estimate.will_be_started} </p>
            <p> Will be completed: {estimate.will_be_completed} </p>
            <p> Expected duration: {estimate.expected_duration} days </p>
            <p>
              {" "}
              Expected mean: {Math.ceil(mean)} {ill} per day{" "}
            </p>
            <form
              className="form start"
              title={`Start the material id=${material.material_id}`}
              onSubmit={(e) => {
                e.preventDefault();
                startMut.mutate(material.material_id);
              }}
            >
              <button type="submit" className="submit-button">
                Start
              </button>
            </form>
          </div>
        );
      })}
    </>
  );
}
