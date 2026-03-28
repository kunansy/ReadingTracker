import { useQuery } from "@tanstack/react-query";
import type { FormEvent } from "react";
import { useSearchParams } from "react-router-dom";

import { apiFetch, buildQuery } from "../../api/notes";

type GraphResponse = {
  iframe_srcdoc: string;
  titles: Record<string, string>;
  material_id: string | null;
};

export function GraphPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const materialId = searchParams.get("material_id") ?? "";

  const q = useQuery({
    queryKey: ["notes", "graph", materialId],
    queryFn: () =>
      apiFetch<GraphResponse>(
        `/graph${buildQuery({ material_id: materialId || undefined })}`,
      ),
  });

  const onSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const mid = String(fd.get("material_id") ?? "").trim();
    if (mid) {
      setSearchParams({ material_id: mid });
    } else {
      setSearchParams({});
    }
  };

  if (q.isLoading) {
    return <p>Loading…</p>;
  }
  if (q.error) {
    return <p className="error">{(q.error as Error).message}</p>;
  }

  const data = q.data;
  const titles = data?.titles ?? {};

  return (
    <>
      <div className="form">
        <form action="#" method="get" onSubmit={onSubmit}>
          <input
            className="input"
            list="books"
            name="material_id"
            defaultValue={materialId}
            placeholder="Choose a material"
          />
          <datalist id="books">
            {Object.entries(titles)
              .sort((a, b) => a[1].localeCompare(b[1]))
              .map(([id, title]) => (
                <option key={id} value={id}>
                  «{title}»
                </option>
              ))}
          </datalist>
          <button type="submit" className="submit-button">
            Search
          </button>
        </form>
      </div>
      {data?.iframe_srcdoc ? (
        <iframe
          title="Notes graph"
          srcDoc={data.iframe_srcdoc}
          className="network"
        />
      ) : null}
    </>
  );
}
