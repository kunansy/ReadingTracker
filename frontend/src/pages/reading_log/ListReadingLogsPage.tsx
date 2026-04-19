import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";

import {apiFetch, buildQuery} from "../../api/readingLog.ts";
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
  const materialId = searchParams.get("material_id") ?? "";

  const materialsTitlesQ = useQuery({
    queryKey: ["materials_titles"],
    queryFn: () =>
        apiFetch<ListMaterialsTitlesResponse>(`/materials-titles`),
  });
  const searchQ = useQuery({
    queryKey: ["reading_logs", "list"],
    queryFn: () =>
      apiFetch<ReadingLogResponse>(`/${buildQuery({
              materialId: materialId || undefined,
          })}`,
        ),
  });

  if (searchQ.isLoading || materialsTitlesQ.isLoading) {
    return <p>Loading…</p>;
  }
  const hasError = searchQ.error || materialsTitlesQ.error;
  if (hasError) {
    return (
      <p className="error">
        {(hasError as Error).message || "Не удалось загрузить данные"}
      </p>
    );
  }

  const data = searchQ.data;
  const materialsTitles = materialsTitlesQ.data;

  return (
    <>
      <div className="form">
        <form
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
