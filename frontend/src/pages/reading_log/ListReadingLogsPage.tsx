import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";

import { apiFetch } from "../../api/readingLog.ts";
import {ListMaterialsTitlesResponse, ListReadingLogsResponse} from "../../types.ts";


export function ListReadingLogsPage() {
    const [searchParams, setSearchParams] = useSearchParams();
    const materialId = searchParams.get("material_id") ?? "";

    const materialsTitlesQ = useQuery({
        queryKey: ["materials", "reading_logs", "titles"],
        queryFn: () => apiFetch<ListMaterialsTitlesResponse>("/materials-titles"),
        staleTime: 5 * 60 * 1000,
    });

    const logsQ = useQuery({
        queryKey: ["logs", { materialId }],
        queryFn: () => {
            const params = materialId ? `?material_id=${materialId}` : '';
            return apiFetch<ListReadingLogsResponse>(`/${params}`);
        },
    });

    const materialsTitles = materialsTitlesQ.data?.items ?? {};
    const data = logsQ.data?.items ?? [];

    if (logsQ.isLoading || materialsTitlesQ.isLoading) {
        return <p>Загрузка...</p>;
    }

    if (logsQ.error || materialsTitlesQ.error) {
        return <p className="error">Error: {((logsQ.error || materialsTitlesQ.error) as Error)?.message}</p>;
    }

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

                    <input
                        className="input"
                        list="materials"
                        name="material_id"
                        defaultValue={materialId}
                        placeholder="Choose a material"
                    />
                    {/*TODO: rewrite with combobox*/}
                    <datalist id="materials">
                        {Object.entries(materialsTitles)
                            .sort((a, b) => a[1].localeCompare(b[1]))
                            .map(([id, title]) => (
                                <option key={id} value={id}>
                                    {" "}
                                    «{title}»{" "}
                                </option>
                            ))}
                    </datalist>
                    <button type="submit" className="submit-button">
                        {" "}
                        Search{" "}
                    </button>
                </form>
            </div>

      <div>
        {data.map((item, index) => {
          const title = materialsTitles[item.material_id] ?? "";
          return (
              <div
              key={item.log_id}
              className="record hover"
              id={item.log_id}
              >
                <p className="little-text">
                  {" "}
                  {index + 1} / {data.length}
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