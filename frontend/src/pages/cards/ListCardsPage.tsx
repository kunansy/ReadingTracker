import { keepPreviousData, useQuery } from "@tanstack/react-query";
import {useNavigate, useSearchParams} from "react-router-dom";

import { api, PAGE_SIZE, unwrap } from "../../api/client";
import {ComboboxInput, ComboboxList, ComboboxRoot} from "../../components/Combobox.tsx";
import {useMemo} from "react";
import {parseMarkdown} from "../../utils/parseMarkdown.ts";
import { ScrollArrows } from "../../components/ScrollArrows";
import { PageNav } from "../../components/PageNav";
import { PageLoadError } from "../../components/PageLoadError";
import { useCursorPagination } from "../../hooks/useCursorPagination";
import { cardKeys } from "../../cards/queries";
import { useMaterialsWithCardsTitles } from "../../materials/queries";


export function ListCardsPage() {
    const [searchParams, setSearchParams] = useSearchParams();
    const materialId = searchParams.get("material_id") ?? "";
    const navigate = useNavigate();
    const pagination = useCursorPagination(PAGE_SIZE, materialId, "desc");
    const nextToken = pagination.cursor;

    const materialsTitlesQ = useMaterialsWithCardsTitles();

    const cardsQ = useQuery({
        queryKey: cardKeys.list({ materialId, nextToken, order: pagination.order }),
        placeholderData: keepPreviousData,
        queryFn: () =>
            unwrap(
                api.GET("/api/v1/cards/", {
                    params: {
                        query: {
                            material_id: materialId || undefined,
                            next_token: nextToken,
                            page_size: PAGE_SIZE,
                            order: pagination.order,
                        },
                    },
                }),
            ),
    });

    const materialsTitles = materialsTitlesQ.data?.items ?? {};
    const data = cardsQ.data?.items ?? [];

    const materialOptions = useMemo(() => {
        return Object.keys(materialsTitles).sort((a, b) =>
            (materialsTitles[a] ?? "").localeCompare(materialsTitles[b] ?? ""),
        );
    }, [materialsTitles]);

    if (cardsQ.isLoading) {
        return <p>Loading...</p>;
    }

    return (
        <>
            {materialsTitlesQ.error ? (
                <p className="error" role="alert">
                    Failed to load materials: {materialsTitlesQ.error.message}
                </p>
            ) : null}
            <div className="form">
                <form
                    id="search-cards-form"
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
                        value={materialId}
                        onChange={(next: string) => {
                            const p = new URLSearchParams(searchParams);
                            if (next) p.set("material_id", next);
                            else p.delete("material_id");
                            setSearchParams(p, { replace: true });
                        }}
                        getOptionLabel={(id) => materialsTitles[id] ?? ""}
                    >
                        <ComboboxInput
                            className="input"
                            placeholder="Choose a material"
                            title="ID of the material"
                        />
                        <ComboboxList />
                    </ComboboxRoot>
                    <button type="submit" className="submit-button">
                        Search
                    </button>
                </form>
            </div>

            {cardsQ.error ? (
              <PageLoadError pagination={pagination} error={cardsQ.error} />
            ) : (
              <>
            <p className="total-cards"> Total { cardsQ.data?.total_count ?? 0 } cards found </p>

      <PageNav
          pagination={pagination}
          nextToken={cardsQ.data?.next_token}
          isBusy={cardsQ.isPlaceholderData}
      />
      <div>
        {data.map((item) => {
          return (
              <div
              key={item.card_id}
              className="card hover"
              id={item.card_id}
              >
                  <p
                      className="question note-content"
                      dangerouslySetInnerHTML={{ __html: parseMarkdown(item.question) }}
                  />
                  <hr className="question-divider"/>
                  <details className="answer">
                      <summary className="answer"> Show answer </summary>
                      {item.answer && (
                          <p
                              className="answer note-content"
                              dangerouslySetInnerHTML={{ __html: parseMarkdown(item.answer) }}
                          />
                      )}
                      <p
                          className="answer note-answer note-content"
                          dangerouslySetInnerHTML={{ __html: parseMarkdown(item.note_content) }}
                      />
                      <p className="txt material-title"> «{ item.material_title }»/{ item.material_authors }/{ item.material_type } </p>
                      <p className="txt material-page"> Chapter: { item.note_chapter } </p>
                      <p className="txt material-page"> Page: { item.note_page } </p>
                      <p
                          className="txt note-id"
                          onClick={async () => {
                            navigate(`/notes/${item.note_id}`);
                          }}
                      >
                          Note ID: {item.note_id}
                      </p>
                  </details>
              </div>
          );
        })}
      </div>
      <PageNav
          pagination={pagination}
          nextToken={cardsQ.data?.next_token}
          isBusy={cardsQ.isPlaceholderData}
      />
              </>
            )}
      <ScrollArrows />
    </>
  );
}