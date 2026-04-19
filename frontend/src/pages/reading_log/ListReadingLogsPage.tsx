import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { apiFetch } from "../../api/readingLog.ts";
import { useContextMenu } from "../../contexts/ContextMenuContext";
import {ComboboxInput, ComboboxList, ComboboxRoot} from "../../components/Combobox.tsx";


type ReadingLogListItem = {
  log_id: string;
  material_id: string;
  date: string;
  count: number;
};

type ReadingLogResponse = {
  items: ReadingLogListItem[];
};

type ListReadingMaterialsResponse = {
  items: Record<string, string>;
}

export function ListReadingLogsPage() {
  const { open, close } = useContextMenu();
  const [searchParams, setSearchParams] = useSearchParams();
  const [materialsTitles, setMaterialsTitles] = useState<ListReadingMaterialsResponse | null>(null);
  const [_, setError] = useState<string | null>(null);
  // const itemRootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    void apiFetch<ListReadingMaterialsResponse>("/materials-titles")
        .then(setMaterialsTitles)
        .catch(() => setError("Failed to load reading materials tags"));
  }, []);

  const materialId = searchParams.get("material_id") ?? "";

  const searchQ = useQuery({
    queryKey: ["reading_logs", "list"],
    queryFn: () =>
      apiFetch<ReadingLogResponse>(`/`),
  });

  const onReadingLogContextMenu = useCallback(
    (e: React.MouseEvent, noteId: string) => {
      e.preventDefault();
      close();
      void (async () => {
        const items: { label: string; action: () => void | Promise<void> }[] = [
          {
            label: "Open",
            action: () => {
              window.open(`/reading_logs/log?log_id=${noteId}`);
            },
          },
          {
            label: "Edit",
            action: () => {
              window.open(`/reading_logs/update-view?note_id=${noteId}`);
            },
          },
          {
            label: "Delete",
            action: () => {
              window.open(`/reading_logs/update-view?note_id=${noteId}`);
            },
          },
        ];
        open(e.clientX, e.clientY, items);
      })();
    },
    [close, open],
  );

  if (searchQ.isLoading) {
    return <p>Loading…</p>;
  }
  if (searchQ.error) {
    return <p className="error">{(searchQ.error as Error).message}</p>;
  }

  const data = searchQ.data;
  if (!data) {
    return null;
  }

  return (
    <>
      <div className="form">
        <form
          key={`${materialId}`}
          id="search-reading-logs-form"
          action="#"
          method="get"
          onSubmit={(e) => {
            e.preventDefault();
            const fd = new FormData(e.currentTarget);
            const next = new URLSearchParams();
            const mid = String(fd.get("material_id") ?? "").trim();
            if (mid) {
              next.set("material_id", mid);
            }
            setSearchParams(next);
          }}
        >
          <ComboboxRoot
              value={materialId || ""}
              onChange={(v) => {
                const next = new URLSearchParams();
                const mid = String(v ?? "").trim();
                if (mid) {
                  next.set("material_id", mid);
                }
                setSearchParams(next);
              }}
              options={[]}
          >
            <ComboboxInput placeholder="Choose a material" />
            <ComboboxList />
          </ComboboxRoot>
          <button type="submit" className="submit-button">
            {" "}
            Search{" "}
          </button>
        </form>
      </div>

      <div>
        {data.items.map((item, index) => {
          const title = materialsTitles?.items[item.material_id] ?? "";
          return (
              <div
              key={item.log_id}
              className="record hover"
              id={item.log_id}
              onContextMenu={(e) => {
                  void onReadingLogContextMenu(e, item.log_id)
              }}
              >
                <p className="little-text">
                  {" "}
                  {index + 1} / {data.items.length}
                </p>
                <p> Date: {item.date} </p>
                <p> Title: «{title}» </p>
                <p> Count: {item.count} </p>
              </div>
          );
        })}

      </div>
       {/*: (*/}
       {/* <div className="not-found">*/}
       {/*   <p className="message"> No reading logs found </p>*/}
       {/* </div>*/}

    </>
  );
}
