import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {useEffect, useMemo, useState} from "react";
import { useSearchParams, useLocation, useNavigate } from "react-router-dom";

import { apiFetch } from "../../api/readingLog";
import { apiFetch as materialsApiFetch } from "../../api/materials.ts";
import { CelebrateButton } from "../../components/CelebrateButton";
import {
  GetMaterialCompletionInfoResponse,
  GetMaterialReadingNowResponse,
  ListMaterialsTitlesResponse,
} from "../../types.ts";
import {isUuid} from "../../utils/isUuid.ts";
import {ComboboxInput, ComboboxList, ComboboxRoot} from "../../components/Combobox.tsx";

export function AddReadingLogPage() {
  const [searchParams] = useSearchParams();
  const initialMaterial = searchParams.get("material_id");

  const [materialId, setMaterialId] = useState(initialMaterial);
  const [date, setDate] = useState("");
  const [count, setCount] = useState("");
  const [error, setError] = useState<string | null>(null);

  const qc = useQueryClient();
  const location = useLocation();
  const navigate = useNavigate();
  const from = location.state?.from || "/materials/reading";

  const materialReadingNowQ = useQuery({
    queryKey: ["materials", "reading_now"],
    queryFn: () =>
        apiFetch<GetMaterialReadingNowResponse>("/material-reading-now"),
  });

  const completionQ = useQuery({
    queryKey: ["materials", materialId, "completion-info"],
    queryFn: () => materialsApiFetch<GetMaterialCompletionInfoResponse>(`/${materialId}/completion-info`),
    enabled: !!materialId && isUuid(materialId),
  });

  const readingMaterialsTitlesQ = useQuery({
    queryKey: ["materials", "reading_titles"],
    queryFn: () => materialsApiFetch<ListMaterialsTitlesResponse>("/reading-titles"),
    staleTime: 5 * 60 * 1000,
  });

  const materialCompletionInfo = completionQ.data;
  const readingMaterialsTitles = readingMaterialsTitlesQ.data;

  useEffect(() => {
    const today = new Date();
    const yyyy = today.getFullYear();
    const mm = String(today.getMonth() + 1).padStart(2, "0");
    const dd = String(today.getDate()).padStart(2, "0");
    setDate(`${yyyy}-${mm}-${dd}`);
  }, []);

  useEffect(() => {
    if (!initialMaterial && materialReadingNowQ.data?.material_id) {
      setMaterialId(materialReadingNowQ.data.material_id);
    }
  }, [materialReadingNowQ.data?.material_id, initialMaterial]);

  const addMut = useMutation({
    mutationFn: async () => {
      if (materialId && !isUuid(materialId)) {
        throw new Error("Choose a valid material (UUID)");
      }
      const body: Record<string, unknown> = {
        material_id: materialId,
        date,
        count: Number(count),
      };
      return apiFetch<{log_id: string }>("/", {
        method: "POST",
        body: JSON.stringify(body),
      });
    },
    onSuccess: (_) => {
      setError(null);
      setCount("");
      setDate("");

      void qc.invalidateQueries({ queryKey: ["reading_logs", "list"] });
      void qc.invalidateQueries({ queryKey: ["materials", "reading"] });
      void qc.invalidateQueries({ queryKey: ["materials", materialId, "completion-info"] });
      navigate(from);
    },
    onError: (e: Error) => {
      setError(e.message);
    },
  });

  const titles = readingMaterialsTitles?.items ?? {};
  const materialOptions = useMemo(() => {
    return Object.keys(titles).sort((a, b) =>
        (titles[a] ?? "").localeCompare(titles[b] ?? ""),
    );
  }, [titles]);

  if (materialReadingNowQ.isLoading || completionQ.isLoading || readingMaterialsTitlesQ.isLoading) {
    return <p>Loading…</p>;
  }
  const hasError = materialReadingNowQ.error || readingMaterialsTitlesQ.error || completionQ.error;
  if (hasError) {
    return (
        <p className="error">
          {(hasError as Error).message || "Failed to load data"}
        </p>
    );
  }

  return (
    <>
      <div className="form">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setError(null);
            addMut.mutate();
          }}
        >
          <fieldset className="fieldset">
            <legend className="legend"> Add reading log </legend>
            <ComboboxRoot
                options={materialOptions}
                getOptionLabel={(id) => titles[id] || id}
                value={materialId || ""}
                onChange={setMaterialId}
            >
              <ComboboxInput
                  placeholder="Choose a material"
                  className="input"
                  title="ID of the material"
              />
              <ComboboxList />
            </ComboboxRoot>

            <p
                className="little-text"
                id="reading-info"
                key="reading-info"
            > { materialCompletionInfo?.pages_read } of { materialCompletionInfo?.material_pages },
              { " " }
              { Math.ceil(materialCompletionInfo?.pages_read / materialCompletionInfo?.material_pages * 100) }
              {"%"}
            </p>

            <input
             className="input"
             type="date"
             placeholder="Enter the date"
             title="Date of the record"
             value={date}
             onChange={(e) => {
               setDate(e.target.value);
             }}
            />
            <input
              className="input"
              type="number"
              placeholder="Enter a count of items"
              title="Count of completed items"
              value={count}
              onChange={(e) => {
                setCount(e.target.value);
              }}
            />
            <CelebrateButton type="submit" className="submit-button">
              Add
            </CelebrateButton>
          </fieldset>
        </form>
      </div>
      {error ? <p className="error">{error}</p> : null}
    </>
  );
}
