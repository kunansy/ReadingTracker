import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useSearchParams, useLocation, useNavigate } from "react-router-dom";

import { apiFetch } from "../../api/readingLog";
import { CelebrateButton } from "../../components/CelebrateButton";
import { useAltchHotkeys } from "../../hooks/useAltchHotkeys";
import { MaterialType } from "../../types.ts";

export function isUuid(value: string): boolean {
  return /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/.test(
    value.trim(),
  );
}

type ListReadingMaterialsTitlesResponse = {
  items: Record<string, string>;
}

type MaterialCompletionInfo = {
  material_pages: number;
  material_type: MaterialType;
  pages_read: number;
  read_days: number;
}

type GetMaterialReadingNow = {
  material_id: string;
}

export function AddReadingLogPage() {
  const [searchParams] = useSearchParams();
  const initialMaterial = searchParams.get("material_id");

  const contentRef = useRef<HTMLTextAreaElement>(null);
  useAltchHotkeys(contentRef);

  const [materialId, setMaterialId] = useState(initialMaterial);
  const [date, setDate] = useState("");
  const [count, setCount] = useState("");
  const [error, setError] = useState<string | null>(null);

  const qc = useQueryClient();
  const location = useLocation();
  const navigate = useNavigate();
  const from = location.state?.from || "/materials/reading";

  const getMaterialReadingNow = useQuery({
    queryKey: ["material_reading_now"],
    queryFn: () =>
        apiFetch<GetMaterialReadingNow>("/material-reading-now"),
  });

  const completionQ = useQuery({
    queryKey: ["material", materialId, "completion-info"],
    queryFn: () => apiFetch<MaterialCompletionInfo>(`/${materialId}/completion-info`),
    enabled: !!materialId && isUuid(materialId),
  });

  const readingMaterialsTitlesQ = useQuery({
    queryKey: ["reading_materials_titles"],
    queryFn: () => apiFetch<ListReadingMaterialsTitlesResponse>("/reading-materials-titles"),
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
    if (!initialMaterial && getMaterialReadingNow.data?.material_id) {
      setMaterialId(getMaterialReadingNow.data.material_id);
    }
  }, [getMaterialReadingNow.data?.material_id, initialMaterial]);

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
      navigate(from);
    },
    onError: (e: Error) => {
      setError(e.message);
    },
  });

  if (getMaterialReadingNow.isLoading || completionQ.isLoading || readingMaterialsTitlesQ.isLoading) {
    return <p>Loading…</p>;
  }
  const hasError = getMaterialReadingNow.error || readingMaterialsTitlesQ.error || completionQ.error;
  if (hasError) {
    return (
        <p className="error">
          {(hasError as Error).message || "Не удалось загрузить данные"}
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
          <fieldset className="log-record-fieldset">
            <legend className="log-record-legend"> Add reading log </legend>
            <input
              id="input_material_id"
              className="input input-datalist"
              list="materials"
              placeholder="Choose a material"
              value={materialId || ""}
              title="ID of the material"
              onChange={(e) => {
                setMaterialId(e.target.value);
              }}
            />
            {/*todo: rewrite with combobox*/}
            <datalist id="materials">
              {Object.entries(readingMaterialsTitles?.items ?? {})
                .sort((a, b) => a[1].localeCompare(b[1]))
                .map(([id, t]) => (
                  <option key={id} value={id}>
                    «{t}»
                  </option>
                ))}
            </datalist>

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
