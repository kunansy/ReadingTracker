import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {useEffect, useMemo, useState} from "react";
import { useSearchParams, useLocation, useNavigate } from "react-router-dom";

import { api, errorMessage, unwrap } from "../../api/client";
import { CelebrateButton } from "../../components/CelebrateButton";
import {isUuid} from "../../utils/isUuid.ts";
import {dateInputValue} from "../../utils/dateInputValue.ts";
import {ComboboxInput, ComboboxList, ComboboxRoot} from "../../components/Combobox.tsx";
import { materialKeys, useMaterialReadingNow, useReadingMaterialTitles } from "../../materials/queries";
import { readingLogKeys } from "../../reading_log/queries";

interface HintButtonProps {
  label: string;
  value: string | undefined;
  current: string;
  showValue?: boolean;
  onPick: (value: string) => void;
}

function HintButton({ label, value, current, showValue = false, onPick }: HintButtonProps) {
  return (
    <button
      type="button"
      className="hint-button"
      data-active={value === current}
      disabled={value === undefined}
      onClick={() => {
        if (value !== undefined) onPick(value);
      }}
    >
      {label}
      {showValue && value !== undefined ? <span className="hint-value">{value}</span> : null}
    </button>
  );
}

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

  const materialReadingNowQ = useMaterialReadingNow();

  const completionQ = useQuery({
    queryKey: materialKeys.completionInfo(materialId ?? ""),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/materials/{material_id}/completion-info", {
          params: { path: { material_id: materialId ?? "" } },
        }),
      ),
    enabled: !!materialId && isUuid(materialId),
  });

  const readingMaterialsTitlesQ = useReadingMaterialTitles();

  const materialCompletionInfo = completionQ.data;
  const readingMaterialsTitles = readingMaterialsTitlesQ.data;

  useEffect(() => {
    setDate(dateInputValue());
  }, []);

  useEffect(() => {
    if (!initialMaterial && materialReadingNowQ.data?.material_id) {
      setMaterialId(materialReadingNowQ.data.material_id);
    }
  }, [materialReadingNowQ.data?.material_id, initialMaterial]);

  const addMut = useMutation({
    mutationFn: async () => {
      if (!materialId || !isUuid(materialId)) {
        throw new Error("Choose a valid material (UUID)");
      }
      return unwrap(
        api.POST("/api/v1/reading_logs/", {
          body: { material_id: materialId, date, count: Number(count) },
        }),
      );
    },
    onSuccess: (_) => {
      setError(null);
      setCount("");
      setDate("");

      void qc.invalidateQueries({ queryKey: readingLogKeys.all });
      void qc.invalidateQueries({ queryKey: materialKeys.reading });
      void qc.invalidateQueries({ queryKey: materialKeys.completionInfo(materialId ?? "") });
      navigate(from);
    },
    onError: (e: unknown) => {
      setError(errorMessage(e));
    },
  });

  const pagesTotal = materialCompletionInfo?.material_pages;
  const pagesRemain = materialCompletionInfo
      ? materialCompletionInfo.material_pages - materialCompletionInfo.pages_read
      : undefined;
  const hasReadingLogs = (materialCompletionInfo?.pages_read ?? 0) > 0;
  const allHint = pagesTotal === undefined ? undefined : String(pagesTotal);
  const remainsHint = pagesRemain === undefined || pagesRemain <= 0 ? undefined : String(pagesRemain);

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
          {hasError.message || "Failed to load data"}
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

            {materialCompletionInfo && materialCompletionInfo.material_pages > 0 ? (
              <p
                  className="little-text"
                  id="reading-info"
                  key="reading-info"
              > { materialCompletionInfo.pages_read } of { materialCompletionInfo.material_pages },
                { " " }
                { Math.ceil(materialCompletionInfo.pages_read / materialCompletionInfo.material_pages * 100) }
                {"%"}
              </p>
            ) : null}

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
            <div className="hints" role="group" aria-label="Date shortcuts">
              <HintButton label="today" value={dateInputValue()} current={date} onPick={setDate} />
              <HintButton label="yesterday" value={dateInputValue(1)} current={date} onPick={setDate} />
            </div>
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
            <div className="hints" role="group" aria-label="Count shortcuts">
              {hasReadingLogs ? (
                <HintButton label="remains" value={remainsHint} current={count} showValue onPick={setCount} />
              ) : (
                <HintButton label="all" value={allHint} current={count} showValue onPick={setCount} />
              )}
            </div>
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
