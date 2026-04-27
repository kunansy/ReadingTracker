import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {useCallback, useEffect, useRef, useState} from "react";
import { useNavigate } from "react-router-dom";

import { apiFetch } from "../../api/materials";
import { NotFoundMaterials } from "../../components/NotFoundMaterials";
import { useContextMenu } from "../../contexts/ContextMenuContext";
import { itemsLabel, itemsLabelLower } from "../../materials/format";
import type {ListMaterialsQueueResponse} from "../../types";
import {CelebrateButton} from "../../components/CelebrateButton.tsx";


export function ListMaterialsQueuePage() {
  const [completeId, setCompleteId] = useState<string | null>(null);
  const [dateStr, setDateStr] = useState("");
  const qc = useQueryClient();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const navigate = useNavigate();
  const { open, close } = useContextMenu();

  const q = useQuery({
    queryKey: ["materials", "queue"],
    queryFn: () => apiFetch<ListMaterialsQueueResponse>("/queue"),
  });

  const startMut = useMutation({
    mutationFn: (p: { materialId: string; startedAt: string}) =>
      apiFetch(`/${p.materialId}/start`, {
        method: "POST",
        body: JSON.stringify({ started_at: p.startedAt }),
      }),
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

  const setToday = () => {
    const today = new Date();
    const yyyy = today.getFullYear();
    const mm = String(today.getMonth() + 1).padStart(2, "0");
    const dd = String(today.getDate()).padStart(2, "0");
    setDateStr(`${yyyy}-${mm}-${dd}`);
  };

  const openStart = (materialId: string) => {
    setCompleteId(materialId);
    setToday();
    dialogRef.current?.showModal();
  };

  useEffect(() => {
    const d = dialogRef.current;
    if (!d) {
      return;
    }
    const onClose = () => {
      setCompleteId(null);
    };
    d.addEventListener("close", onClose);
    return () => {
      d.removeEventListener("close", onClose);
    };
  }, []);

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
            navigate(`/materials/update?material_id=${materialId}`, {
              state: { from: location.pathname + location.search },
            })
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
            <div
                className="form start"
                title={`Start the material id=${material.material_id}`}
            >
              <button
                  type="button"
                  className="submit-button celebrate-btn"
                  onClick={() => {
                    openStart(material.material_id);
                  }}
              >
                Start
              </button>
            </div>


            <dialog
                ref={dialogRef}
                id="complete-material-dialog"
                className="complete-material-dialog"
            >
              <p className="complete-material-dialog__title">Completion date</p>
              <p>
                <label className="complete-material-dialog__label">
                  Date{" "}
                  <input
                      type="date"
                      id="complete-material-date"
                      className="complete-material-dialog__date"
                      required
                      value={dateStr}
                      onChange={(e) => {
                        setDateStr(e.target.value);
                      }}
                  />
                </label>
              </p>
              <div className="complete-material-dialog__actions">
                <button
                    type="button"
                    id="complete-material-cancel"
                    className="submit-button"
                    onClick={() => {
                      dialogRef.current?.close();
                    }}
                >
                  Cancel
                </button>
                <CelebrateButton
                    id="complete-material-confirm"
                    className="submit-button celebrate-btn"
                    onClick={async () => {
                      if (!completeId || !dateStr) {
                        return;
                      }
                      try {
                        await startMut.mutateAsync({
                          materialId: completeId,
                          startedAt: dateStr,
                        });
                        dialogRef.current?.close();
                      } catch (err) {
                        window.alert((err as Error).message);
                      }
                    }}
                >
                  Start
                </CelebrateButton>
              </div>
            </dialog>

          </div>
        );
      })}
    </>
  );
}
