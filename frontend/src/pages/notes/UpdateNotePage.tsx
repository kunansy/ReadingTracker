import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import { apiFetch, buildQuery } from "../../api/notes";
import { apiFetch as materialsApiFetch } from "../../api/materials";
import { CelebrateButton } from "../../components/CelebrateButton";
import { useAltchHotkeys } from "../../hooks/useAltchHotkeys";
import {
  GetNoteResponse,
  GetNoteTagsResponse,
  ListMaterialsTitlesResponse, ListPossibleLinkResponse,
} from "../../types.ts";
import { ComboboxInput, ComboboxList, ComboboxRoot } from "../../components/Combobox.tsx";
import { useSpellChecker } from "../../hooks/useSpellChecker.ts";
import { SpellErrorsList } from "../../components/SpellErrorsList.tsx";
import {isUuid} from "../../utils/isUuid.ts";


function demarkNote(s: string): string {
  return s;
  // todo
  // return s.replaceAll("&lt;", "<").replaceAll("&gt;", ">");
}

export function UpdateNotePage() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const contentRef = useRef<HTMLTextAreaElement>(null);
  useAltchHotkeys(contentRef);

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

  const { spellErrors, replaceWord } = useSpellChecker(content, setContent);

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
  const possibleLinksQ = useQuery({
    queryKey: ["possible-links", noteId],
    enabled: Boolean(noteId),
    queryFn: () => apiFetch<ListPossibleLinkResponse>(`/possible-links${buildQuery({note_id: noteId})}`),
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
      await qc.invalidateQueries({ queryKey: ["possible-links", noteId] });
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
            <fieldset className="fieldset">
              <legend className="legend"> Update </legend>

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
                  style={{
                    height: "30vh",
                  }}
              />

              <SpellErrorsList spellErrors={spellErrors} onReplace={replaceWord} />

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

        {possibleLinksQ.data?.items.length ? (
            <div
                className="links-list"
                style={{
                  display: "flex",
                  flexDirection: "row",
                  overflow: "scroll",
                  margin: "16px auto",
                  maxWidth: "80%",
                  gap: "12px",
                  alignItems: "flex-start",
                }}
            >
              {possibleLinksQ.data.items.map((link) => (
                  <div
                      key={link.note_id}
                      className="links-list-item"
                      style={{
                        border: "2px solid #333",
                        borderRadius: "12px",
                        padding: "16px",
                        minWidth: "280px",
                        maxWidth: "35vw",
                        wordBreak: "break-word",
                        lineHeight: "1.4",
                        fontSize: "14px",
                      }}
                      title={link.title}
                      onClick={() => {
                        setLinkId(link.note_id);
                      }}
                  >
                    <div
                        style={{
                            flexGrow: 1,
                            minHeight: 0,
                        }}
                    >
                      {link.content}
                    </div>
                  </div>
              ))}
            </div>
        ) : null}

        {error ? <p className="error">{error}</p> : null}
      </>
  );
}