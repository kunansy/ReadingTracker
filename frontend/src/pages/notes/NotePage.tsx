import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { apiFetch } from "../../api/notes";
import {GetNoteResponse} from "@/types.ts";

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

  if (!noteId) {
    return <p className="error">Invalid note id</p>;
  }
  if (q.isLoading) {
    return <p>Loading…</p>;
  }
  if (q.error) {
    return <p className="error">{(q.error as Error).message}</p>;
  }

  const n = q.data?.note;
  if (!n) {
    return null;
  }

  return (
    <div className="note-page-root">
      <div className="form">
        <div className="note-page-actions">
          <Link className="submit-button" to={`/notes/${n.note_id}/edit`}>
            Edit
          </Link>
          <Link className="submit-button" to="/notes">
            Back
          </Link>
        </div>
      </div>

      <div className={`note ${n.is_deleted ? "deleted" : ""}`} id={n.note_id}>
        <p className="little-text">Note id: {n.note_id}</p>
        <p className="little-text">Material id: {n.material_id}</p>
        <p className="little-text">Added: {n.added_at}</p>
        <p className="little-text">Number: {n.note_number}</p>
        {n.title ? <p className="note-title large-text">«{n.title}»</p> : null}
        <p className="note-content" dangerouslySetInnerHTML={{ __html: n.content }} />
        {n.tags?.length ? (
          <p className="note-content">
            {n.tags
              .slice()
              .sort((a, b) => a.localeCompare(b))
              .map((t) => `#${t}`)
              .join(" ")}
          </p>
        ) : null}
        {n.link_id ? <p className="medium-text">Link: [[{n.link_id}]]</p> : null}
        <p className="note-page">Chapter: {n.chapter || "-"}</p>
        <p className="note-page">Page: {n.page}</p>
        {typeof n.links_count === "number" ? (
          <p className="medium-text" title="How many notes link to this one">
            Links count: {n.links_count}
          </p>
        ) : null}
        {n.is_deleted ? <p className="error">Deleted</p> : null}
      </div>
    </div>
  );
}

