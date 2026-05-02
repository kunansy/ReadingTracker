import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import { apiFetch } from "../../api/notes";
import { apiFetch as materialsApiFetch  } from "../../api/materials";
import { CelebrateButton } from "../../components/CelebrateButton";
import { useAltchHotkeys } from "../../hooks/useAltchHotkeys";
import { GetNoteResponse, GetNoteTagsResponse, ListMaterialsTitlesResponse } from "../../types.ts";
import {ComboboxInput, ComboboxList, ComboboxRoot} from "../../components/Combobox.tsx";


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

export function NoteEditPage() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const contentRef = useRef<HTMLTextAreaElement>(null);
  useAltchHotkeys(contentRef);

  const { noteId: noteIdParam } = useParams();
  const [searchParams] = useSearchParams();
  const noteIdQuery = searchParams.get("note_id") ?? "";

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
    queryKey: ["notes", "tags"],
    queryFn: () => apiFetch<GetNoteTagsResponse>(`/tags`),
    staleTime: 5 * 60 * 1000,
  });

  const [materialId, setMaterialId] = useState("");
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [tags, setTags] = useState("");
  const [linkId, setLinkId] = useState("");
  const [chapter, setChapter] = useState("");
  const [page, setPage] = useState("");
  const [error, setError] = useState<string | null>(null);

  const updateMut = useMutation({
    mutationFn: async () => {
      if (!noteId || !isUuid(noteId)) {
        throw new Error("Missing note_id");
      }
      if (!isUuid(materialId)) {
        throw new Error("Choose a valid material (UUID)");
      }
      const body: Record<string, unknown> = {
        note_id: noteId,
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
    setTags((n.tags ?? []).map((t) => `#${t}`).join(" "));
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
                onChange={(next: string) => {
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
            <ComboboxRoot
                value={tags}
                onChange={setTags}
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
              min={0}
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

