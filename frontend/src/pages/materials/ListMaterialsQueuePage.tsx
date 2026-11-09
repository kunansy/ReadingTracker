import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {useCallback, useEffect, useRef, useState} from "react";
import { useNavigate } from "react-router-dom";

import { api, errorMessage, PAGE_SIZE, unwrap, unwrapEmpty } from "../../api/client";
import { NotFoundMaterials } from "../../components/NotFoundMaterials";
import { useContextMenu } from "../../contexts/ContextMenuContext";
import { itemsLabel, itemsLabelLower } from "../../materials/format";
import {CelebrateButton} from "../../components/CelebrateButton.tsx";
import { ScrollArrows } from "../../components/ScrollArrows";
import { dateInputValue } from "../../utils/dateInputValue";
import { PageNav } from "../../components/PageNav";
import { PageLoadError } from "../../components/PageLoadError";
import { useCursorPagination } from "../../hooks/useCursorPagination";
import { materialKeys } from "../../materials/queries";

export function ListMaterialsQueuePage() {
  const [completeId, setCompleteId] = useState<string | null>(null);
  const [dateStr, setDateStr] = useState("");
  const qc = useQueryClient();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const navigate = useNavigate();
  const { open, close } = useContextMenu();
  const pagination = useCursorPagination(PAGE_SIZE, "", "desc");
  const nextToken = pagination.cursor;

  const q = useQuery({
    queryKey: materialKeys.queueList(nextToken, pagination.order),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/materials/queue", {
          params: {
            query: {
              next_token: nextToken,
              page_size: PAGE_SIZE,
              order: pagination.order,
            },
          },
        }),
      ),
    placeholderData: keepPreviousData,
  });

  const startMut = useMutation({
    mutationFn: (p: { materialId: string; startedAt: string}) =>
      unwrapEmpty(
        api.POST("/api/v1/materials/{material_id}/start", {
          params: { path: { material_id: p.materialId } },
          body: { started_at: p.startedAt },
        }),
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: materialKeys.all });
    },
  });

  const setToday = () => {
    setDateStr(dateInputValue());
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
    (e: React.MouseEvent, materialId: string) => {
      e.preventDefault();
      close();
      open(e.clientX, e.clientY, [
        {
          label: "Edit",
          action: () => {
            navigate(`/materials/update?material_id=${materialId}`, {
              state: { from: location.pathname + location.search },
            });
          },
        },
      ]);
    },
    [close, navigate, open],
  );

  if (q.isLoading) {
    return <p>Loading…</p>;
  }
  if (q.error) {
    return <PageLoadError pagination={pagination} error={q.error} />;
  }
  const data = q.data;
  if (!data?.estimates?.length) {
    return <NotFoundMaterials kind="materials" />;
  }

  return (
    <>
      <PageNav
        pagination={pagination}
        nextToken={data.next_token}
        isBusy={q.isPlaceholderData}
      />
      {data.estimates.map((estimate, i) => {
        const material = estimate.material;
        const il = itemsLabel(material.material_type);
        const ill = itemsLabelLower(material.material_type);
        const mean = data.mean[material.material_type];
        return (
          <div
            key={material.material_id}
            className="material hover queue-item"
            id={material.material_id}
            onContextMenu={(e) => onQueueContextMenu(e, material.material_id)}
          >
            <p className="little-text">
              {" "}
              {pagination.offset + i + 1} / {data.total_count}
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
              Expected mean: {mean === undefined ? "n/a" : `${Math.ceil(mean)} ${ill} per day`}{" "}
            </p>
            <div
                className="form start"
                title={`Start the material id=${material.material_id}`}
            >
              <button
                  type="button"
                  className="submit-button"
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
                    className="submit-button"
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
                        navigate("/materials/reading#header");
                      } catch (err) {
                        window.alert(errorMessage(err));
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
      <PageNav
        pagination={pagination}
        nextToken={data.next_token}
        isBusy={q.isPlaceholderData}
      />
      <ScrollArrows />
    </>
  );
}
