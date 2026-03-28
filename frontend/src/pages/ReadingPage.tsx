import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";

import { apiFetch } from "../api/materials";
import { CelebrateButton } from "../components/CelebrateButton";
import { NotFoundMaterials } from "../components/NotFoundMaterials";
import { useContextMenu } from "../contexts/ContextMenuContext";
import { itemsLabel, itemsLabelLower } from "../materials/format";
import type { MaterialStatisticsJson } from "../types";

type ReadingResponse = {
  statistics: MaterialStatisticsJson[];
};

export function ReadingPage() {
  const qc = useQueryClient();
  const { open, close } = useContextMenu();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [completeId, setCompleteId] = useState<string | null>(null);
  const [dateStr, setDateStr] = useState("");

  const q = useQuery({
    queryKey: ["materials", "reading"],
    queryFn: () => apiFetch<ReadingResponse>("/reading"),
  });

  const completeMut = useMutation({
    mutationFn: (p: { materialId: string; completedAt: string }) =>
      apiFetch(`/${p.materialId}/complete`, {
        method: "POST",
        body: JSON.stringify({ completed_at: p.completedAt }),
      }),
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
          label: "Open reading log",
          action: async () => {
            window.open(`/reading_log/?material_id=${materialId}`);
          },
        },
        {
          label: "Add note",
          action: async () => {
            window.open(`/notes/add-view?material_id=${materialId}`);
          },
        },
        {
          label: "Add reading log",
          action: async () => {
            window.open(`/reading_log/add-view?material_id=${materialId}`);
          },
        },
      ]);
    },
    [close, open],
  );

  const setToday = () => {
    const today = new Date();
    const yyyy = today.getFullYear();
    const mm = String(today.getMonth() + 1).padStart(2, "0");
    const dd = String(today.getDate()).padStart(2, "0");
    setDateStr(`${yyyy}-${mm}-${dd}`);
  };

  const openComplete = (materialId: string) => {
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

  if (q.isLoading) {
    return <p>Loading…</p>;
  }
  if (q.error) {
    return <p className="error">{(q.error as Error).message}</p>;
  }
  const stats = q.data?.statistics;
  if (!stats?.length) {
    return <NotFoundMaterials kind="reading materials" />;
  }

  return (
    <>
      {stats.map((ms) => {
        const material = ms.material;
        const il = itemsLabel(material.material_type);
        const ill = itemsLabelLower(material.material_type);
        return (
          <div
            key={material.material_id}
            className="material hover reading"
            id={material.material_id}
            onContextMenu={(e) => onMaterialContextMenu(e, material.material_id)}
          >
            <p> Title: «{material.title}» </p>
            <p> Author: {material.authors} </p>
            <p>
              {" "}
              {il}: {material.pages}{" "}
            </p>
            <p> Type: {material.material_type} </p>
            {material.tags ? <p> Tags: {material.tags} </p> : null}
            {material.link ? <p> Link: {material.link} </p> : null}
            <hr title="Analytics" />
            <p> Started at: {ms.started_at} </p>
            <p> Is being reading: {ms.duration} days </p>
            <p> Total duration: {ms.total_reading_duration} </p>
            <p>
              {" "}
              Total {ill} completed: {ms.total}, {ms.percent_completed}%{" "}
            </p>
            <p> Notes count: {ms.notes_count} notes </p>
            <p>
              {" "}
              Mean: {ms.mean} {ill} per day{" "}
            </p>
            <p> Lost time: {ms.lost_time} days </p>
            <hr title="Remains" />
            <p>
              {" "}
              Remaining {ill}: {ms.remaining_pages}{" "}
            </p>
            <p> Remaining days: {ms.remaining_days} </p>
            <p> Would be completed: {ms.would_be_completed} </p>
            {ms.max_record && ms.min_record ? (
              <>
                <hr title="Min/max" />
                <p>
                  {" "}
                  Max: {ms.max_record.count} {ill}, {ms.max_record.date}{" "}
                </p>
                <p>
                  {" "}
                  Min: {ms.min_record.count} {ill}, {ms.min_record.date}{" "}
                </p>
              </>
            ) : null}
            <div
              className="complete"
              title={`Complete the material id=${material.material_id}`}
            >
              <button
                type="button"
                className="submit-button celebrate-btn complete-material-open"
                onClick={() => {
                  openComplete(material.material_id);
                }}
              >
                Complete
              </button>
            </div>
          </div>
        );
      })}

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
            className="btn btn-secondary"
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
                await completeMut.mutateAsync({
                  materialId: completeId,
                  completedAt: dateStr,
                });
                dialogRef.current?.close();
              } catch (err) {
                window.alert((err as Error).message);
              }
            }}
          >
            Complete
          </CelebrateButton>
        </div>
      </dialog>
    </>
  );
}
