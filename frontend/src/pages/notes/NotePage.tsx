import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { useParams, useSearchParams} from "react-router-dom";

import {apiFetch} from "../../api/notes";
import { apiFetch as materialsApiFetch } from "../../api/materials";
import {GetNoteResponse, GetMaterialResponse} from "../../types.ts";

function isUuid(value: string): boolean {
  return /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/.test(
    value.trim(),
  );
}

export function NotePage() {
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
  const materialQ = useQuery({
    queryKey: ["materials", q.data?.note.material_id],
    enabled: Boolean(q.data?.note.material_id),
    queryFn: () => materialsApiFetch<GetMaterialResponse>(`/${q.data?.note.material_id}`),
  });

  if (!noteId) {
    return <p className="error">Invalid note id</p>;
  }
  if (q.isLoading || materialQ.isLoading) {
    return <p>Loading…</p>;
  }
  if (q.error || materialQ.error) {
    return <p className="error">{((q.error || materialQ.error) as Error).message}</p>;
  }

  const note = q.data?.note;
  const material = materialQ.data?.material;
  if (!n || !material) {
    return null;
  }

  return (
    <div className="note-page-root">
      <div className={`note ${note.is_deleted ? "deleted" : ""}`} id={note.note_id}>
        <p className="little-text">Note number: {note.note_number}</p>
        <p className="medium-text hover">Note id: {note.note_id}</p>
        {note.title ? <p className="note-title large-text">«{note.title}»</p> : null}
        <p className="note-content" dangerouslySetInnerHTML={{ __html: note.content }} />
        {note.tags?.length ? (
          <div
              className="note-tags"
              style={{
                display: "flex",
                margin: "auto",
                flexDirection: "row",
                gap: "5px",
              }}
          >
            {note.tags.map((t) => {
                return (
                  <a
                      className="note-tag"
                      href={`/notes?tags_query=${t}`}
                  >
                    #{t}
                  </a>
                )
              })}
          </div>
        ) : null}
        <p className="medium-text">Page: {note.page} of {material.pages}</p>
        <p className="medium-text">Added at: {note.added_at}</p>
        <hr/>
        <p className="medium-text">Material id: {material.material_id}</p>
        <p className="medium-text">Material title: «{material.title}»</p>
        <p className="medium-text">Material authors: {material.authors}</p>
        <p className="medium-text">Material type: {material.material_type}</p>
        <p className="medium-text">Is material outlined: {material.is_outlined ? "Yes" : "No"}</p>
        {note.link_id ? <p className="medium-text">Link: [[{note.link_id}]]</p> : null}
        {typeof note.links_count === "number" ? (
          <p className="medium-text" title="How many notes link to this one">
            Links count: {note.links_count}
          </p>
        ) : null}
        {note.is_deleted ? <p className="error">Deleted</p> : null}
      </div>

      <iframe
        className="iframe"
        src={`/api/v1/notes/links-network?note_id=${note.note_id}`}
      />
    </div>
  );
}

