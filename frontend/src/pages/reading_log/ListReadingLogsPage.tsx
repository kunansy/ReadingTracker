import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { apiFetch } from "../../api/readingLog.ts";
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

type ListMaterialsTitlesResponse = {
  items: Record<string, string>;
}

export function ListReadingLogsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [materialsTitles, setMaterialsTitles] = useState<ListMaterialsTitlesResponse | null>(null);
  const [_, setError] = useState<string | null>(null);
  // const itemRootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    void apiFetch<ListMaterialsTitlesResponse>("/materials-titles")
        .then(setMaterialsTitles)
        .catch(() => setError("Failed to load reading materials tags"));
  }, []);

  const materialId = searchParams.get("material_id") ?? "";

  const searchQ = useQuery({
    queryKey: ["reading_logs", "list"],
    queryFn: () =>
      apiFetch<ReadingLogResponse>(`/`),
  });

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
