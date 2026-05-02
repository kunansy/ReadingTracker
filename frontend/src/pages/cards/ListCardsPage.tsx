import { useQuery } from "@tanstack/react-query";
import {useNavigate, useSearchParams} from "react-router-dom";

import { apiFetch } from "../../api/cards.ts";
import {ListMaterialsTitlesResponse, ListCardsResponse} from "../../types.ts";
import {ComboboxInput, ComboboxList, ComboboxRoot} from "../../components/Combobox.tsx";
import {useMemo} from "react";


export function ListCardsPage() {
    const [searchParams, setSearchParams] = useSearchParams();
    const materialId = searchParams.get("material_id") ?? "";
    const navigate = useNavigate();

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

    const materialOptions = useMemo(() => {
        return Object.keys(materialsTitles).sort((a, b) =>
            (materialsTitles[a] ?? "").localeCompare(materialsTitles[b] ?? ""),
        );
    }, [materialsTitles]);

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
                            className="input input-datalist"
                            id="material_id"
                            placeholder="Choose a material"
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
       {/*: (*/}
       {/* <div className="not-found">*/}
       {/*   <p className="message"> No cards found </p>*/}
       {/* </div>*/}
    </>
  );
}