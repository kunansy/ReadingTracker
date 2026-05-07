import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import { apiFetch, buildQuery } from "../../api/notes";
import { apiFetch as materialsApiFetch } from "../../api/materials";
import { CelebrateButton } from "../../components/CelebrateButton";
import { useAltchHotkeys } from "../../hooks/useAltchHotkeys";
import {
  GetNoteResponse,
  GetNoteTagsResponse,
  ListMaterialsTitlesResponse,
} from "../../types.ts";
import { ComboboxInput, ComboboxList, ComboboxRoot } from "../../components/Combobox.tsx";


function isUuid(value: string): boolean {
  return /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/.test(
    value.trim(),
  );
}

function demarkNote(s: string): string {
  return s;
  // todo
  // return s.replaceAll("&lt;", "<").replaceAll("&gt;", ">");
}

type SpellError = {
  word: string;
  suggestions: string[];
};

export function NoteEditPage() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const contentRef = useRef<HTMLTextAreaElement>(null);
  useAltchHotkeys(contentRef);

  const spellAbortRef = useRef<AbortController | null>(null);
  const debounceRef = useRef<number | null>(null);

  const { noteId: noteIdParam } = useParams();
  const [searchParams] = useSearchParams();
  const noteIdQuery = searchParams.get("note_id") ?? "";

  const [materialId, setMaterialId] = useState("");
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [tags, setTags] = useState<string[]>([]);
  const [linkId, setLinkId] = useState("");
  const [chapter, setChapter] = useState("");
  const [page, setPage] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [spellErrors, setSpellErrors] = useState<SpellError[]>([]);

  const replaceWord = useCallback((error: SpellError, suggestion: string) => {
    const newContent = content.replaceAll(error.word, suggestion);
    setContent(newContent);

    setSpellErrors(prevErrors => prevErrors.filter(e => e.word !== error.word));
  }, [content]);

  useEffect(() => {
    return () => {
      if (debounceRef.current !== null) {
        window.clearTimeout(debounceRef.current);
      }
      spellAbortRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    if (debounceRef.current !== null) {
      window.clearTimeout(debounceRef.current);
      debounceRef.current = null;
    }
    spellAbortRef.current?.abort();
    spellAbortRef.current = null;

    const text = content.trim();
    if (!text) {
      setSpellErrors([]);
      return;
    }

    debounceRef.current = window.setTimeout(async () => {
      const controller = new AbortController();
      spellAbortRef.current = controller;

      try {
        const resp = await fetch(
            `https://speller.yandex.net/services/spellservice.json/checkText?text=${encodeURIComponent(content)}`,
            {
              method: "GET",
              signal: controller.signal,
            },
        );

        if (!resp.ok) {
          throw new Error(`Spell checker request failed: ${resp.status}`);
        }

        const errata: Array<{ word: string; s?: string[] }> = await resp.json();

        if (!controller.signal.aborted) {
          setSpellErrors(
              (errata ?? []).map((e) => ({
                word: e.word,
                suggestions: e.s ?? [],
              })),
          );
        }
      } catch (e: any) {
        if (e?.name !== "AbortError") {
          setSpellErrors([]);
        }
      } finally {
        if (spellAbortRef.current === controller) {
          spellAbortRef.current = null;
        }
      }
    }, 750);

    return () => {
      if (debounceRef.current !== null) {
        window.clearTimeout(debounceRef.current);
        debounceRef.current = null;
      }
      spellAbortRef.current?.abort();
    };
  }, [content]);

  const noteId = useMemo(() => {
    const fromParam = (noteIdParam ?? "").trim();
    if (fromParam && isUuid(fromParam)) {
      return fromParam;
    }
    const fromQuery = noteIdQuery.trim();
    if (fromQuery && isUuid(fromQuery)) {
      return fromQuery;
    }
    return "";
  }, [noteIdParam, noteIdQuery]);

  const q = useQuery({
    queryKey: ["notes", noteId],
    enabled: Boolean(noteId),
    queryFn: () => apiFetch<GetNoteResponse>(`/${noteId}`),
  });
  const materialTitlesQ = useQuery({
    queryKey: ["materials", "titles"],
    queryFn: () => materialsApiFetch<ListMaterialsTitlesResponse>(`/titles`),
  });
  const noteTagsQ = useQuery({
    queryKey: ["notes", "tags", materialId],
    enabled: isUuid(materialId),
    queryFn: () => apiFetch<GetNoteTagsResponse>(`/tags${buildQuery({material_id: materialId || undefined})}`),
  });

  const updateMut = useMutation({
    mutationFn: async () => {
      if (!noteId || !isUuid(noteId)) {
        throw new Error("Missing note_id");
      }
      if (!isUuid(materialId)) {
        throw new Error("Choose a valid material (UUID)");
      }
      const body: Record<string, unknown> = {
        material_id: materialId,
        title: title.trim() ? title.trim() : null,
        content,
        tags,
        link_id: linkId.trim() && isUuid(linkId.trim()) ? linkId.trim() : null,
        chapter: chapter || "",
        page: page === "" ? 0 : Number(page),
      };
      await apiFetch(`/${noteId}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      });
    },
    onSuccess: async () => {
      setError(null);
      await qc.invalidateQueries({ queryKey: ["notes", noteId] });
      await qc.invalidateQueries({ queryKey: ["notes"] });
      navigate(`/notes/${noteId}`);
    },
    onError: (e: Error) => {
      setError(e.message);
    },
  });

  const titles = materialTitlesQ.data?.items ?? {};
  const materialOptions = useMemo(() => {
    return Object.keys(titles).sort((a, b) =>
        (titles[a] ?? "").localeCompare(titles[b] ?? ""),
    );
  }, [titles]);

  useEffect(() => {
    const n = q.data?.note;
    if (!n) {
      return;
    }
    setMaterialId(n.material_id);
    setTitle(n.title ?? "");
    setContent(demarkNote(n.content));
    setTags(n.tags ?? []);
    setLinkId(n.link_id ?? "");
    setChapter(n.chapter ?? "");
    setPage(String(n.page ?? 0));
  }, [q.data, noteId]);

  if (!noteId) {
    return <p className="error">Invalid note id</p>;
  }
  if (q.isLoading || materialTitlesQ.isLoading || noteTagsQ.isLoading) {
    return <p>Loading…</p>;
  }
  if (q.error || materialTitlesQ.isError || noteTagsQ.isError) {
    return <p className="error">{((q.error || materialTitlesQ.error || noteTagsQ.error) as Error).message}</p>;
  }

  const isDeleted = q.data?.note.is_deleted ?? false;
  const noteTags = noteTagsQ.data?.tags ?? [];

  return (
      <>
      {isDeleted ? <p className="error">This note is deleted. Editing may be unsafe.</p> : null}

        <div className="form">
          <form
              onSubmit={(e) => {
                e.preventDefault();
                setError(null);
                updateMut.mutate();
              }}
          >
            <fieldset className="add-note-fieldset">
              <legend className="add-note-legend"> Edit note </legend>

              <ComboboxRoot
                  options={materialOptions}
                  value={materialId}
                  onChange={(next) => {
                    setMaterialId(next);
                  }}
                  getOptionLabel={(id) => titles[id] ?? ""}
              >
                <ComboboxInput className="input" placeholder="Choose a material" />
                <ComboboxList />
              </ComboboxRoot>
              <input
                  className="input"
                  placeholder="Enter a title"
                  value={title}
                  onChange={(e) => {
                    setTitle(e.target.value);
                  }}
              />
              <textarea
                  ref={contentRef}
                  className="input altch"
                  id="input-content"
                  placeholder="Enter a content"
                  value={content}
                  onChange={(e) => {
                    setContent(e.target.value);
                  }}
              />
              {spellErrors.length > 0 ? (
                  <p className="error" id="input-content-errata">
                    {spellErrors.map((err, errorIdx) =>
                            err.suggestions.length > 0 ? (
                                <div key={errorIdx}>
                                  <strong>{err.word}:</strong>
                                  <span>
                        {err.suggestions.map((suggestion) => (
                            <button
                                key={suggestion}
                                className="suggestion-btn"
                                onClick={(e) => {
                                  e.preventDefault();
                                  replaceWord(err, suggestion);
                                }}
                                style={{
                                  margin: "0 4px 4px 0",
                                  padding: "2px 6px",
                                  background: "#fff3cd",
                                  border: "1px solid #ffeaa7",
                                  borderRadius: "4px",
                                  cursor: "pointer",
                                  fontSize: "14px",
                                }}
                            >
                              {suggestion}
                            </button>
                        ))}
                      </span>
                                  <br />
                                </div>
                            ) : (
                                <span key={errorIdx}>
                      {err.word} (исправлений нет)
                      <br />
                    </span>
                            ),
                    )}
                  </p>
              ) : null}
              <ComboboxRoot
                  value={tags}
                  onChange={(e) => {
                    setTags(e);
                  }}
                  options={noteTags}
                  multiple
                  allowCreate
              >
                <ComboboxInput placeholder="Enter tags" />
                <ComboboxList />
              </ComboboxRoot>
              <input
                  className="input"
                  placeholder="Enter a link"
                  value={linkId}
                  onChange={(e) => {
                    setLinkId(e.target.value);
                  }}
              />
              <input
                  className="input"
                  placeholder="Enter a chapter"
                  value={chapter}
                  onChange={(e) => {
                    setChapter(e.target.value);
                  }}
              />
              <input
                  className="input"
                  type="number"
                  placeholder="Enter a page number"
                  value={page}
                  onChange={(e) => {
                    setPage(e.target.value);
                  }}
              />
              <CelebrateButton type="submit" className="submit-button">
                Save
              </CelebrateButton>
            </fieldset>
          </form>
        </div>

        {error ? <p className="error">{error}</p> : null}
      </>
  );
}