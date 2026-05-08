import { useQuery } from "@tanstack/react-query";
import { useMemo, useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { apiFetch, buildQuery } from "../../api/notes";
import { apiFetch as materialsApiFetch } from "../../api/materials";
import { GetMaterialResponse, GetNoteLinksResponse, GetNoteResponse, MaterialType } from "../../types";
import { NetworkIframe } from "../../components/NetworkIframe";
import { QueryStateFromResult } from "../../components/QueryState";
import {parseMarkdown} from "../../utils/parseMarkdown.ts";
import {isUuid} from "../../utils/isUuid.ts";

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
    queryFn: () =>
      materialsApiFetch<GetMaterialResponse>(`/${q.data?.note.material_id}`),
  });

  const noteLinksQ = useQuery({
    queryKey: ["notes", "links", noteId],
    enabled: Boolean(noteId),
    queryFn: () =>
      apiFetch<GetNoteLinksResponse>(`/links${buildQuery({ note_id: noteId })}`),
  });

  useEffect(() => {
    const materialType = materialQ.data?.material.material_type || MaterialType.book;
    setPageName("Page");
    if (materialType === MaterialType.lecture || materialType === MaterialType.audiobook) {
      setPageName("Minute");
    }
    if (materialType === MaterialType.course) {
      setPageName("Lecture");
    }
  }, [materialQ.data?.material.material_type]);

  if (!noteId) {
    return <p className="error">Invalid note id</p>;
  }

  return (
    <>
    <div className="note-root-page">
      <QueryStateFromResult
        query={q}
        loading={<p>Loading note…</p>}
        errorRenderer={(err) => <p className="error">Note error: {err instanceof Error ? err.message : String(err)}</p>}
      >
        {(noteResponse: GetNoteResponse | undefined) => {
          const note = noteResponse?.note;
          if (!note) {
            return <p>Note not found</p>;
          }

          return (
            <>
              <div className="to-link">
                {noteLinksQ.data?.link_to ? (
                  <div
                    className="note-link"
                    onClick={() => navigate(`/notes/${noteLinksQ.data?.link_to.note_id}`)}
                    title={noteLinksQ.data.link_to.info}
                  />
                ) : null}
              </div>

              <div className={`note ${note.is_deleted ? "deleted" : ""}`} id={note.note_id}>
                <p className="little-text">Note number: {note.note_number}</p>
                <p className="medium-text hover">Note id: {note.note_id}</p>
                {note.title ? (
                  <p className="note-title large-text">«{note.title}»</p>
                ) : null}
                <p
                  className="note-content"
                  dangerouslySetInnerHTML={{ __html: parseMarkdown(note.content) }}
                />
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
                    {note.tags.map((t) => (
                      <Link
                        key={t}
                        className="note-tag"
                        to={`/notes?tags_query=${t}`}
                      >
                        #{t}
                      </Link>
                    ))}
                  </div>
                ) : null}
                {note.link_id ? (
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
                  </p>
                ) : null}
                <p className="medium-text">{pageName}: {note.page} of {materialQ.data?.material.pages}</p>
                <p className="medium-text">Added at: {note.added_at}</p>
                <hr />

                <QueryStateFromResult
                  query={materialQ}
                  loading={<p className="medium-text">Loading material info…</p>}
                  errorRenderer={(err) => (
                    <p className="error">Material error: {err instanceof Error ? err.message : String(err)}</p>
                  )}
                >
                  {( materialResponse: GetMaterialResponse | undefined ) => {
                    const material = materialResponse?.material;
                    if (!material) {
                      return <p>Note not found</p>;
                    }
                    return <>
                      <p className="medium-text">Material id: {material.material_id}</p>
                      <p className="medium-text">Material title: «{material.title}»</p>
                      <p className="medium-text">Material authors: {material.authors}</p>
                      <p className="medium-text">Material type: {material.material_type}</p>
                      <p className="medium-text">
                        Is material outlined: {material.is_outlined ? "Yes" : "No"}
                      </p>
                    </>
                  }}
                </QueryStateFromResult>

                {typeof note.links_count === "number" ? (
                  <p className="medium-text" title="How many notes link to this one">
                    Links count: {note.links_count}
                  </p>
                ) : null}

                {note.is_deleted ? <p className="error">Deleted</p> : null}
              </div>

              <QueryStateFromResult
                query={noteLinksQ}
                loading={<p>Loading note links…</p>}
                errorRenderer={(err) => (
                  <p className="error">Links error: {err instanceof Error ? err.message : String(err)}</p>
                )}
              >
                {( linksFromResponse: GetNoteLinksResponse | undefined) => {
                  const links_from = linksFromResponse?.links_from;
                  if (!links_from) {
                    return <p>Note links not found</p>;
                  }
                  return links_from.length ? (
                    <div className="from-links">
                      {links_from.map((link) => (
                        <div
                          className="note-link"
                          key={link.note_id}
                          onClick={() => navigate(`/notes/${link.note_id}`)}
                          title={link.info}
                        />
                      ))}
                    </div>
                  ) : null;
                }}
              </QueryStateFromResult>
            </>
          );
        }}
      </QueryStateFromResult>
    </div>

      {Boolean(noteId) && isUuid(noteId) ? (
        <NetworkIframe
          key={noteId}
          src={`/api/v1/notes/links-network?note_id=${noteId}`}
          title="Note links network"
        />
      ): null}
      </>
  );
}