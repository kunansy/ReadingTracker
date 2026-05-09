import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";

import { apiFetch, buildQuery } from "../../api/readingLog.ts";
import { apiFetch as materialsApiFetch } from "../../api/materials.ts";
import {ListMaterialsTitlesResponse, ListReadingLogsResponse} from "../../types.ts";
import {ComboboxInput, ComboboxList, ComboboxRoot} from "../../components/Combobox.tsx";

export function ListReadingLogsPage() {
    const [searchParams, setSearchParams] = useSearchParams();
    const materialId = searchParams.get("material_id") ?? "";

    const materialsTitlesQ = useQuery({
        queryKey: ["materials", "read_titles"],
        queryFn: () => materialsApiFetch<ListMaterialsTitlesResponse>("/read-titles"),
        staleTime: 5 * 60 * 1000,
    });

    const logsQ = useQuery({
        queryKey: ["logs", { materialId }],
        queryFn: () => {
            return apiFetch<ListReadingLogsResponse>(`/${buildQuery({material_id: materialId || undefined})}`);
        },
    });

    const materialsTitles = materialsTitlesQ.data?.items ?? {};
    const data = logsQ.data?.items ?? [];

    const materialOptions = useMemo(() => {
        return Object.keys(materialsTitles).sort((a, b) =>
            (materialsTitles[a] ?? "").localeCompare(materialsTitles[b] ?? ""),
        );
    }, [materialsTitlesQ]);

    if (logsQ.isLoading || materialsTitlesQ.isLoading) {
        return <p>Loading...</p>;
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

                    <ComboboxRoot
                        options={materialOptions}
                        getOptionLabel={(id) => materialsTitles[id] || id}
                        value={materialId}
                        onChange={(e) => {
                            const next = new URLSearchParams();
                            next.set("material_id", e);
                            setSearchParams(next);
                        }}
                    >
                        <ComboboxInput
                            placeholder="Choose a material"
                            className="input"
                            title="ID of the material"
                        />
                        <ComboboxList />
                    </ComboboxRoot>

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