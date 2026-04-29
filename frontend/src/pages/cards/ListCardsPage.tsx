import { useQuery } from "@tanstack/react-query";
import {useSearchParams} from "react-router-dom";

import { apiFetch } from "../../api/cards.ts";
import {ListMaterialsTitlesResponse, ListCardsResponse} from "../../types.ts";


export function ListCardsPage() {
    const [searchParams, setSearchParams] = useSearchParams();
    const materialId = searchParams.get("material_id") ?? "";

    const materialsTitlesQ = useQuery({
        queryKey: ["materials", "cards", "titles"],
        queryFn: () => apiFetch<ListMaterialsTitlesResponse>("/materials-titles"),
        staleTime: 5 * 60 * 1000,
    });

    const cardsQ = useQuery({
        queryKey: ["cards", { materialId }],
        queryFn: () => {
            const params = materialId ? `?material_id=${materialId}` : '';
            return apiFetch<ListCardsResponse>(`/${params}`);
        },
    });

    const materialsTitles = materialsTitlesQ.data?.items ?? {};
    const data = cardsQ.data?.items ?? [];

    if (cardsQ.isLoading || materialsTitlesQ.isLoading) {
        return <p>Загрузка...</p>;
    }

    if (cardsQ.error || materialsTitlesQ.error) {
        return <p className="error">Error: {((cardsQ.error || materialsTitlesQ.error) as Error)?.message}</p>;
    }

    return (
        <>
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

            <p className="total-cards"> Total { data.length } cards found </p>

      <div>
        {data.map((item) => {
          return (
              <div
              key={item.card_id}
              className="card hover"
              id={item.card_id}
              >
                  <p className="question"> { item.question } </p>
                  <hr className="question-divider"/>
                  <details className="answer">
                      <summary className="answer"> Show answer </summary>
                      {item.answer && <p className="answer">{item.answer}</p>}
                      <p className="answer note-answer"> { item.note_content } </p>
                      <p className="txt material-title"> «{ item.material_title }»/{ item.material_authors }/{ item.material_type } </p>
                      <p className="txt material-page"> Chapter: { item.note_chapter } </p>
                      <p className="txt material-page"> Page: { item.note_page } </p>
                      <p
                          className="txt note-id"
                          onClick={async () => {
                            window.open(`/notes/note?note_id=${item.note_id}`, "_blank");
                          }}
                      >
                          Note ID: {item.note_id}
                      </p>
                  </details>
              </div>
          );
        })}
      </div>
       {/*: (*/}
       {/* <div className="not-found">*/}
       {/*   <p className="message"> No cards found </p>*/}
       {/* </div>*/}
    </>
  );
}