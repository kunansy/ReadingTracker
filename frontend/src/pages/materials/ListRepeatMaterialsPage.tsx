import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {useNavigate, useSearchParams} from "react-router-dom";

import { api, PAGE_SIZE, unwrap } from "../../api/client";
import { CelebrateButton } from "../../components/CelebrateButton";
import { NotFoundMaterials } from "../../components/NotFoundMaterials";
import { useContextMenu } from "../../contexts/ContextMenuContext";
import { itemsLabel } from "../../materials/format";
import { ScrollArrows } from "../../components/ScrollArrows";
import { PageNav } from "../../components/PageNav";
import { PageLoadError } from "../../components/PageLoadError";
import { useCursorPagination } from "../../hooks/useCursorPagination";

export function ListRepeatMaterialsPage() {
  const qc = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const { open } = useContextMenu();

  const onlyOutlined =
    searchParams.get("only_outlined") === "on" ||
    searchParams.get("only_outlined") === "true";

  const pagination = useCursorPagination(PAGE_SIZE, String(onlyOutlined), "asc");
  const nextToken = pagination.cursor;

  const query = {
    only_outlined: onlyOutlined || undefined,
    next_token: nextToken,
    page_size: PAGE_SIZE,
    order: pagination.order,
  };

  const q = useQuery({
    queryKey: ["materials", "repeat", query],
    placeholderData: keepPreviousData,
    queryFn: () => unwrap(api.GET("/api/v1/materials/repeat", { params: { query } })),
  });

  const repeatMut = useMutation({
    mutationFn: (materialId: string) =>
      unwrap(
        api.POST("/api/v1/materials/{material_id}/repeat", {
          params: { path: { material_id: materialId } },
        }),
      ),
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
    return <PageLoadError pagination={pagination} error={q.error} />;
  }

  const rows = q.data?.repeating_queue ?? [];

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

      <PageNav
        pagination={pagination}
        nextToken={q.data?.next_token}
        isBusy={q.isPlaceholderData}
      />
      {!rows.length ? (
        <NotFoundMaterials kind="repeating queue" />
      ) : (
        rows.map((repeat, idx) => {
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
                navigate(`/notes?material_id=${repeat.material_id}`);
              }}
              onContextMenu={async (e) => {
                if (repeat.notes_count === 0 && repeat.notes_count === 0) {
                  return;
                }
                e.preventDefault();
                const items = [
                  {
                    label: `Open notes (${repeat.notes_count})`,
                    action: async () => {
                      navigate(`/notes/?material_id=${encodeURIComponent(repeat.material_id)}`);
                    },
                  },
                ];
                if (repeat.cards_count !== 0) {
                  items.push({
                    label: `Open cards (${repeat.cards_count})`,
                    action: async () => {
                      navigate(`/cards/?material_id=${encodeURIComponent(repeat.material_id)}`);
                    },
                  })
                }

                open(e.clientX, e.clientY, items);
              }}
            >
              <p className="little-text">
                {pagination.offset + idx + 1} / {q.data?.total_count ?? 0}
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
              </div>
            </div>
          );
        })
      )}
      <PageNav
        pagination={pagination}
        nextToken={q.data?.next_token}
        isBusy={q.isPlaceholderData}
      />
      <ScrollArrows />
    </>
  );
}
