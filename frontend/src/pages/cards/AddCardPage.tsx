import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";

import { apiFetch as cardsApiFetch } from "../../api/cards";
import { apiFetch as notesApiFetch, buildQuery } from "../../api/notes";
import { CelebrateButton } from "../../components/CelebrateButton";
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
    enabled: !!materialId && isUuid(materialId),
    queryFn: () =>
      notesApiFetch<NotesSearchResponse>(
        `/search${buildQuery({ material_id: materialId, page: 1, page_size: 200 })}`,
      ),
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

  if (metaQ.isLoading || notesQ.isLoading) {
    return <p>Loading…</p>;
  }
  if (metaQ.error || notesQ.error) {
    return (
      <p className="error">
        {((metaQ.error || notesQ.error) as Error)?.message ||
          "Не удалось загрузить данные"}
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
          <input
            className="input input-datalist"
            id="material_id"
            list="materials"
            placeholder="Choose a material"
            value={materialId}
            title="ID of the material"
            onChange={(e) => {
              const next = e.target.value;
              setMaterialId(next);
              const p = new URLSearchParams(searchParams);
              if (next) p.set("material_id", next);
              else p.delete("material_id");
              p.delete("note_id");
              setSearchParams(p, { replace: true });
            }}
          />
          {/* TODO: rewrite with combobox */}
          <datalist id="materials">
            {Object.entries(materialsTitles)
              .sort((a, b) => a[1].localeCompare(b[1]))
              .map(([id, t]) => (
                <option key={id} value={id}>
                  «{t}»
                </option>
              ))}
          </datalist>

          <input
            className="input input-datalist"
            id="note_id"
            list="notes"
            placeholder="Choose a note"
            value={noteId}
            onChange={(e) => {
              const next = e.target.value;
              setNoteId(next);
              const p = new URLSearchParams(searchParams);
              if (next) p.set("note_id", next);
              else p.delete("note_id");
              setSearchParams(p, { replace: true });
            }}
          />
          <datalist id="notes">
            {notes.map((n) => (
              <option key={n.note_id} value={n.note_id}>
                {stripHtml(n.content_html)}
              </option>
            ))}
          </datalist>

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
                className="note hover"
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
      ) : null}

      {error ? <p className="error">{error}</p> : null}
    </>
  );
}
