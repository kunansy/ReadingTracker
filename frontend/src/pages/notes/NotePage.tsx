import {useQuery} from "@tanstack/react-query";
import {useEffect, useMemo, useState} from "react";
import {Link, useNavigate, useParams, useSearchParams} from "react-router-dom";

import {apiFetch, buildQuery} from "../../api/notes";
import {apiFetch as materialsApiFetch} from "../../api/materials";
import {GetMaterialResponse, GetNoteLinksResponse, GetNoteResponse, MaterialType} from "../../types.ts";
import {NetworkIframe} from "../../components/NetworkIframe.tsx";

function isUuid(value: string): boolean {
  return /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/.test(
    value.trim(),
  );
}

export function NotePage() {
  const { noteId: noteIdParam } = useParams();
  const [searchParams] = useSearchParams();
  const noteIdQuery = searchParams.get("note_id") ?? "";
  const navigate = useNavigate();
  const [pageName, setPageName] = useState("Page");

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
  const noteLinksQ = useQuery({
    queryKey: ["notes", "links", noteId],
    enabled: Boolean(noteId),
    queryFn: () => apiFetch<GetNoteLinksResponse>(`/links${buildQuery({note_id: noteId})}`),
  });

  useEffect(() => {
    const materialType = materialQ.data?.material.material_type || MaterialType.book;
    setPageName("Page");
    if (materialType == MaterialType.lecture || materialType == MaterialType.audiobook) {
      setPageName("Minute");
    }
    if (materialType == MaterialType.course) {
      setPageName("Lecture");
    }
  }, [materialQ.data?.material.material_type])

  if (!noteId) {
    return <p className="error">Invalid note id</p>;
  }
  if (q.isLoading || materialQ.isLoading || noteLinksQ.isLoading) {
    return <p>Loading…</p>;
  }
  if (q.error || materialQ.error || noteLinksQ.error) {
    return <p className="error">{((q.error || materialQ.error || noteLinksQ.error) as Error).message}</p>;
  }

  const note = q.data?.note;
  const material = materialQ.data?.material;
  const noteLinks = noteLinksQ.data;
  if (!note || !material || !noteLinks) {
    return null;
  }

  return (
      <>
      <div className="note-root-page">
        {noteLinks.link_to ? (
          <div className="to-link">
            <div
              className="note-link"
              onClick={() => navigate(`/notes/${noteLinks.link_to.note_id}`)}
              title={noteLinks.link_to.info}
            />
          </div>
        ) : null}

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
                    <Link
                        className="note-tag"
                        to={`/notes?tags_query=${t}`}
                    >
                      #{t}
                    </Link>
                  )
                })}
            </div>
          ) : null}
          {note.link_id ?
              <p className="note-content">
                <Link
                  to={`/notes/${note.link_id}`}
                  style={{
                    textAlign: "left",
                    fontSize: "2.5vh",
                  }}
                >
                  [[{note.link_id}]]
                </Link>
              </p> : null}
          <p className="medium-text">{pageName}: {note.page} of {material.pages}</p>
          <p className="medium-text">Added at: {note.added_at}</p>
          <hr/>
          <p className="medium-text">Material id: {material.material_id}</p>
          <p className="medium-text">Material title: «{material.title}»</p>
          <p className="medium-text">Material authors: {material.authors}</p>
          <p className="medium-text">Material type: {material.material_type}</p>
          <p className="medium-text">Is material outlined: {material.is_outlined ? "Yes" : "No"}</p>
          {typeof note.links_count === "number" ? (
            <p className="medium-text" title="How many notes link to this one">
              Links count: {note.links_count}
            </p>
          ) : null}
          {note.is_deleted ? <p className="error">Deleted</p> : null}
        </div>

        {noteLinks.links_from.length ? (
          <div className="from-links">
            {noteLinks.links_from.map((link) => {
              return (
                <div
                  className="note-link"
                  key={link.note_id}
                  onClick={() => navigate(`/notes/${link.note_id}`)}
                  title={link.info}
                />
              )
            })}
            </div>
        ) : null}
      </div>

      <NetworkIframe key={note.note_id} src={`/api/v1/notes/links-network?note_id=${note.note_id}`}/>
    </>
  );
}

