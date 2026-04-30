import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";

import { apiFetch as cardsApiFetch } from "../../api/cards";
import { apiFetch as notesApiFetch, buildQuery } from "../../api/notes";
import { CelebrateButton } from "../../components/CelebrateButton";
import {
  ComboboxInput,
  ComboboxList,
  ComboboxRoot,
} from "../../components/Combobox";
import { useAltchHotkeys } from "../../hooks/useAltchHotkeys";

type NoteListItem = {
  note_id: string;
  material_id: string;
  content_html: string;
  chapter: string;
  page: number;
};

type NotesSearchResponse = {
  notes: NoteListItem[];
  total_count: number;
};

type NotesMetaResponse = {
  titles: Record<string, string>;
};

type CreateCardResponse = {
  card_id: string;
};

type NotesWithCardsResponse = {
  items: string[];
};

export function isUuid(value: string): boolean {
  return /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/.test(
    value.trim(),
  );
}

function stripHtml(html: string): string {
  const tmp = document.createElement("div");
  tmp.innerHTML = html;
  return (tmp.textContent ?? "").trim();
}

export function AddCardPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const initialMaterialId = searchParams.get("material_id") ?? "";
  const initialNoteId = searchParams.get("note_id") ?? "";

  const questionRef = useRef<HTMLTextAreaElement>(null);
  useAltchHotkeys(questionRef);

  const [materialId, setMaterialId] = useState<string>(initialMaterialId);
  const [noteId, setNoteId] = useState<string>(initialNoteId);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [error, setError] = useState<string | null>(null);

  const qc = useQueryClient();
  const location = useLocation();
  const navigate = useNavigate();
  const from = location.state?.from || "/cards";

  useEffect(() => {
    setMaterialId(initialMaterialId);
  }, [initialMaterialId]);

  useEffect(() => {
    setNoteId(initialNoteId);
  }, [initialNoteId]);

  const metaQ = useQuery({
    queryKey: ["notes", "meta"],
    queryFn: () => notesApiFetch<NotesMetaResponse>("/meta"),
    staleTime: 10 * 60 * 1000,
  });

  const notesQ = useQuery({
    queryKey: ["notes", "search", { materialId }],
    queryFn: () =>
      notesApiFetch<NotesSearchResponse>(
        `/search${buildQuery({
          ...(isUuid(materialId) ? { material_id: materialId } : {}),
          page: 1,
          page_size: 200,
        })}`,
      ),
  });

  const notesWithCardsQ = useQuery({
    queryKey: ["cards", "notes-with-cards", { materialId }],
    queryFn: () =>
      cardsApiFetch<NotesWithCardsResponse>(
        `/notes-with-cards${buildQuery({
          ...(isUuid(materialId) ? { material_id: materialId } : {}),
        })}`,
      ),
    staleTime: 30_000,
  });

  const addMut = useMutation({
    mutationFn: async () => {
      const mid = materialId.trim();
      const nid = noteId.trim();
      const q = question.trim();
      const a = answer.trim();

      if (!isUuid(mid)) {
        throw new Error("Choose a valid material (UUID)");
      }
      if (!isUuid(nid)) {
        throw new Error("Choose a valid note (UUID)");
      }
      if (!q) {
        throw new Error("Question is required");
      }

      return cardsApiFetch<CreateCardResponse>("/", {
        method: "POST",
        body: JSON.stringify({
          material_id: mid,
          note_id: nid,
          question: q,
          answer: a || null,
        }),
      });
    },
    onSuccess: () => {
      setError(null);
      setQuestion("");
      setAnswer("");

      void qc.invalidateQueries({ queryKey: ["cards"] });
      navigate(from);
    },
    onError: (e: Error) => {
      setError(e.message);
    },
  });

  const materialsTitles = metaQ.data?.titles ?? {};
  const notes = notesQ.data?.notes ?? [];
  const notesWithCards = useMemo(() => {
    return new Set((notesWithCardsQ.data?.items ?? []).map((x) => x.trim()));
  }, [notesWithCardsQ.data?.items]);

  const materialOptions = useMemo(() => {
    return Object.keys(materialsTitles).sort((a, b) =>
      (materialsTitles[a] ?? "").localeCompare(materialsTitles[b] ?? ""),
    );
  }, [materialsTitles]);

  const notesById = useMemo(() => {
    const m = new Map<string, NoteListItem>();
    for (const n of notes) m.set(n.note_id, n);
    return m;
  }, [notes]);

  useEffect(() => {
    if (noteId) {
      const note = notesById.get(noteId);
      if (note) {
        setQuestion((prev) => (prev.trim() ? prev : stripHtml(note.content_html)));
      }
    }
  }, [noteId, notesById]);

  const noteOptions = useMemo(() => notes.map((n) => n.note_id), [notes]);

  if (metaQ.isLoading || notesQ.isLoading || notesWithCardsQ.isLoading) {
    return <p>Loading…</p>;
  }
  if (metaQ.error || notesQ.error || notesWithCardsQ.error) {
    return (
      <p className="error">
        {((metaQ.error || notesQ.error || notesWithCardsQ.error) as Error)?.message ||
          "Не удалось загрузить данные"}
      </p>
    );
  }

  return (
    <>
      {!!materialId && isUuid(materialId) ? (
          <div className="notes">
            <h3 id="srch-label" className="search-notes-label">
              Search notes | {notesQ.data?.total_count ?? 0} items
            </h3>
            {materialsTitles[materialId] ? (
                <h3 className="material-title">«{materialsTitles[materialId]}»</h3>
            ) : null}
            <ul className="notes" id="notes-list">
              {notes.map((n) => (
                  <li
                      key={n.note_id}
                      className={[
                        "note",
                        "hover",
                        notesWithCards.has(n.note_id) ? "with_card" : "without_card",
                      ].join(" ")}
                      id={`note-${n.note_id}`}
                      title="Click to choose this note"
                      onClick={() => {
                        setNoteId(n.note_id);
                        if (!question.trim()) {
                          setQuestion(stripHtml(n.content_html));
                        }
                        const p = new URLSearchParams(searchParams);
                        p.set("note_id", n.note_id);
                        setSearchParams(p, { replace: true });
                      }}
                  >
                    <p
                        className="note-content"
                        dangerouslySetInnerHTML={{ __html: n.content_html }}
                    />
                    <p className="note-page">Page: {n.page}</p>
                    <p className="note-id">ID: {n.note_id}</p>
                  </li>
              ))}
            </ul>
          </div>
      ) : (
          <div className="notes">
            <h3 id="srch-label" className="search-notes-label">
              Search notes | {notesQ.data?.total_count ?? 0} items
            </h3>
            <ul className="notes" id="notes-list">
              {notes.map((n) => (
                  <li
                      key={n.note_id}
                      className={[
                        "note",
                        "hover",
                        notesWithCards.has(n.note_id) ? "with_card" : "without_card",
                      ].join(" ")}
                      id={`note-${n.note_id}`}
                      title="Click to choose this note"
                      onClick={() => {
                        setMaterialId(n.material_id);
                        setNoteId(n.note_id);
                        if (!question.trim()) {
                          setQuestion(stripHtml(n.content_html));
                        }

                        const p = new URLSearchParams(searchParams);
                        p.set("material_id", n.material_id);
                        p.set("note_id", n.note_id);
                        setSearchParams(p, { replace: true });
                      }}
                  >
                    <p
                        className="note-content"
                        dangerouslySetInnerHTML={{ __html: n.content_html }}
                    />
                    <p className="note-page">Page: {n.page}</p>
                    <p className="note-id">ID: {n.note_id}</p>
                  </li>
              ))}
            </ul>
          </div>
      )}

      <div className="form">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setError(null);
            addMut.mutate();
          }}
        >
          <ComboboxRoot
            options={materialOptions}
            value={materialId}
            onChange={(next: string) => {
              setMaterialId(next);
              setNoteId("");
              setQuestion("");
              setAnswer("");

              const p = new URLSearchParams(searchParams);
              if (next) p.set("material_id", next);
              else p.delete("material_id");
              p.delete("note_id");
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

          <ComboboxRoot
            options={noteOptions}
            value={noteId}
            onChange={(next: string) => {
              const n = notesById.get(next);
              if (n) {
                // legacy behavior: choosing a note sets both fields
                setMaterialId(n.material_id);
                setNoteId(n.note_id);
                setQuestion("");
                setAnswer("");
                if (!question.trim()) {
                  setQuestion(stripHtml(n.content_html));
                }
                const p = new URLSearchParams(searchParams);
                p.set("material_id", n.material_id);
                p.set("note_id", n.note_id);
                setSearchParams(p, { replace: true });
                return;
              }

              // fallback if user typed a UUID that's not in current notes list
              setNoteId(next);
              const p = new URLSearchParams(searchParams);
              if (next) p.set("note_id", next);
              else p.delete("note_id");
              setSearchParams(p, { replace: true });
            }}
            getOptionLabel={(id) => {
              const n = notesById.get(id);
              return n ? stripHtml(n.content_html) : "";
            }}
          >
            <ComboboxInput
              className="input input-datalist"
              id="note_id"
              placeholder="Choose a note"
            />
            <ComboboxList />
          </ComboboxRoot>

          <textarea
            ref={questionRef}
            className="input altch"
            id="input-question"
            placeholder="Enter a question"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
          />
          <textarea
            className="input altch"
            id="input-answer"
            placeholder="Enter an answer (optional)"
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
          />

          <CelebrateButton type="submit" className="submit-button">
            Add
          </CelebrateButton>
        </form>
      </div>

      {error ? <p className="error">{error}</p> : null}
    </>
  );
}
