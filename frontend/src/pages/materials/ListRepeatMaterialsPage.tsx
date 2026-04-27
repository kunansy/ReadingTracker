import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {useNavigate, useSearchParams} from "react-router-dom";

import { apiFetch, buildQuery } from "../../api/materials";
import { CelebrateButton } from "../../components/CelebrateButton";
import { NotFoundMaterials } from "../../components/NotFoundMaterials";
import { useContextMenu } from "../../contexts/ContextMenuContext";
import { itemsLabel } from "../../materials/format";
import type { GetRepeatingQueueResponse } from "../../types";

export function ListRepeatMaterialsPage() {
  const qc = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const { open } = useContextMenu();

  const onlyOutlined =
    searchParams.get("only_outlined") === "on" ||
    searchParams.get("only_outlined") === "true";

  const queryString = buildQuery({
    only_outlined: onlyOutlined ? "true" : undefined,
  });

  const q = useQuery({
    queryKey: ["materials", "repeat", queryString],
    queryFn: () => apiFetch<GetRepeatingQueueResponse>(`/repeat${queryString}`),
  });

  const repeatMut = useMutation({
    mutationFn: (materialId: string) =>
      apiFetch(`/${materialId}/repeat`, { method: "POST" }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["materials"] });
    },
  });

  const onFilterSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const checked = fd.get("only_outlined") === "on";
    if (checked) {
      setSearchParams({ only_outlined: "on" });
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

  const rows = q.data?.repeating_queue ?? [];
  const sorted = [...rows].sort((a, b) => b.priority_months - a.priority_months);

  return (
    <>
      <div className="form">
        <form action="#" method="get" onSubmit={onFilterSubmit}>
          <div className="outlined-checkbox">
            <input
              id="only_outlined"
              className="input"
              type="checkbox"
              name="only_outlined"
              defaultChecked={onlyOutlined}
            />
            <label htmlFor="only_outlined"> Only outlined </label>
          </div>
          <button type="submit" className="submit-button">
            Search
          </button>
        </form>
      </div>

      {!sorted.length ? (
        <NotFoundMaterials kind="repeating queue" />
      ) : (
        sorted.map((repeat, idx) => {
          const il = itemsLabel(repeat.material_type);
          const isOutlined = repeat.is_outlined ? "Yes" : "No";
          const lastRepeated = repeat.last_repeated_at
            ? repeat.last_repeated_at.slice(0, 10)
            : "No";
          return (
            <div
              key={repeat.material_id}
              className="repeat hover"
              id={repeat.material_id}
              title="Click to see notes"
              onClick={() => {
                navigate(`/notes?material_id=${repeat.material_id}&page_size=${repeat.notes_count}`);
              }}
              onContextMenu={async (e) => {
                if (repeat.cards_count === 0) {
                  return;
                }
                e.preventDefault();
                open(e.clientX, e.clientY, [
                  {
                    label: `Open cards (${repeat.cards_count})`,
                    action: async () => {
                      window.open(
                          // todo: navigate
                        `/cards/list?material_id=${encodeURIComponent(repeat.material_id)}`,
                      );
                    },
                  },
                ]);
              }}
            >
              <p className="little-text">
                {idx + 1} / {sorted.length}
              </p>
              <p> Title: «{repeat.title}» </p>
              <p>
                {il}: {repeat.pages}
              </p>
              <p> Is outlined: {isOutlined} </p>
              <hr title="Analytics" />
              <p> Completed at: {repeat.completed_at?.slice(0, 10) ?? ""} </p>
              <p> Notes count: {repeat.notes_count} notes </p>
              <p> Cards count: {repeat.cards_count} cards </p>
              <p> Repeats count: {repeat.repeats_count} repeats </p>
              <p> Last repeated at: {lastRepeated} </p>
              <p> Priority: {repeat.priority_months.toFixed(1)} </p>
              <div className="repeat-btns">
                <form
                  className="repeat"
                  title="Repeat the material"
                  onClick={(e) => {
                    e.stopPropagation();
                  }}
                  onSubmit={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    repeatMut.mutate(repeat.material_id);
                  }}
                >
                  <CelebrateButton type="submit" className="submit-button">
                    Repeat
                  </CelebrateButton>
                </form>
                {repeat.cards_count > 0 ? (
                  <form
                    className="open-cards"
                    title="Open material cards"
                    onClick={(e) => {
                      e.stopPropagation();
                    }}
                    onSubmit={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      // todo: navigate
                      window.open(
                        `/cards/list?material_id=${encodeURIComponent(repeat.material_id)}`,
                      );
                    }}
                  >
                    <CelebrateButton type="submit" className="submit-button">
                      Open cards ({repeat.cards_count})
                    </CelebrateButton>
                  </form>
                ) : null}
              </div>
            </div>
          );
        })
      )}
    </>
  );
}
