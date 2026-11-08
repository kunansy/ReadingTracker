import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {useNavigate, useSearchParams} from "react-router-dom";

import { apiFetch, buildQuery } from "../../api/notes";
import { useContextMenu } from "../../contexts/ContextMenuContext";
import {parseMarkdown} from "../../utils/parseMarkdown.ts";
import { ScrollArrows } from "../../components/ScrollArrows";
import { PageNav } from "../../components/PageNav";
import { PageLoadError } from "../../components/PageLoadError";
import { useCursorPagination } from "../../hooks/useCursorPagination";

type NoteListItem = {
  note_id: string;
  material_id: string;
  title: string | null;
  content_html: string;
  tags_html: string;
  link_html: string;
  chapter: string;
  chapter_int: number;
  page: number;
  links_count: number;
  is_deleted?: boolean;
};

type SearchResponse = {
  notes: NoteListItem[];
  total_count: number;
  titles: Record<string, string>;
  material_types: Record<string, string>;
  material_notes: Record<string, number>;
  chapters: Record<string, string[]>;
  query: string | null;
  tags: string[];
  tags_query: string | null;
  next_token: string | null;
  page_size: number;
  material_id: string | null;
};

type MetaResponse = {
  titles: Record<string, string>;
  tags: string[];
};

const PAGE_SIZE = 10;

function groupNotesByMaterialAndChapter(notes: NoteListItem[]) {
  const order: string[] = [];
  const seen = new Set<string>();
  for (const n of notes) {
    if (!seen.has(n.material_id)) {
      seen.add(n.material_id);
      order.push(n.material_id);
    }
  }
  const out: {
    materialId: string;
    chapters: { chapter: string; notes: NoteListItem[] }[];
  }[] = [];
  for (const materialId of order) {
    const matNotes = notes.filter((x) => x.material_id === materialId);
    const byChapter = new Map<number, NoteListItem[]>();
    for (const n of matNotes) {
      const k = n.chapter_int;
      const arr = byChapter.get(k) ?? [];
      arr.push(n);
      byChapter.set(k, arr);
    }
    const chapters = [...byChapter.entries()]
      .sort((a, b) => a[0] - b[0])
      .map(([, chNotes]) => {
        const sorted = [...chNotes].sort((a, b) => a.page - b.page);
        return { chapter: sorted[0]?.chapter ?? "", notes: sorted };
      });
    out.push({ materialId, chapters });
  }
  return out;
}

function labelsForMaterialType(t: string | undefined) {
  if (t === "lecture") {
    return { pageName: "Minute", chapterName: "Chapter" };
  }
  if (t === "course") {
    return { pageName: "Lecture", chapterName: "Block" };
  }
  return { pageName: "Page", chapterName: "Chapter" };
}

export function SearchNotesPage() {
  const qc = useQueryClient();
  const { open, close } = useContextMenu();
  const [searchParams, setSearchParams] = useSearchParams();
  const notesRootRef = useRef<HTMLDivElement>(null);

  const materialId = searchParams.get("material_id") ?? "";
  const query = searchParams.get("query") ?? "";
  const tagsQuery = searchParams.get("tags_query") ?? "";
  const navigate = useNavigate();
  const pagination = useCursorPagination(
    PAGE_SIZE,
    JSON.stringify([materialId, query, tagsQuery]),
    "asc",
  );
  const nextToken = pagination.cursor;

  const [hintList, setHintList] = useState<string[]>([]);

  const metaQ = useQuery({
    queryKey: ["notes", "meta", materialId],
    queryFn: () =>
      apiFetch<MetaResponse>(`/meta${buildQuery({ material_id: materialId || undefined })}`),
  });

  const searchQ = useQuery({
    queryKey: ["notes", "search", materialId, query, tagsQuery, nextToken, pagination.order],
    placeholderData: keepPreviousData,
    queryFn: () =>
      apiFetch<SearchResponse>(
        `/search${buildQuery({
          material_id: materialId || undefined,
          query: query || undefined,
          tags_query: tagsQuery || undefined,
          next_token: nextToken,
          page_size: PAGE_SIZE,
          order: pagination.order,
        })}`,
      ),
  });

  const titles = metaQ.data?.titles ?? {};
  const hasTitles = Object.keys(titles).length > 0;

  const searchData = searchQ.data;

  const grouped = useMemo(
    () => (searchData?.notes ? groupNotesByMaterialAndChapter(searchData.notes) : []),
    [searchData?.notes],
  );

  const indexByNoteId = useMemo(() => {
    const m = new Map<string, number>();
    let i = pagination.offset;
    for (const g of grouped) {
      for (const ch of g.chapters) {
        for (const n of ch.notes) {
          i += 1;
          m.set(n.note_id, i);
        }
      }
    }
    return m;
  }, [grouped, pagination.offset]);

  const deleteMut = useMutation({
    mutationFn: async (noteId: string) => {
      await apiFetch(`/${encodeURIComponent(noteId)}`, { method: "DELETE" });
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["notes"] });
    },
  });

  const restoreMut = useMutation({
    mutationFn: async (noteId: string) => {
      await apiFetch(`/${encodeURIComponent(noteId)}/restore`, { method: "POST" });
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["notes"] });
    },
  });

  const onNoteContextMenu = useCallback(
    (e: React.MouseEvent, note: {note_id: string, material_id: string, is_deleted?: boolean, has_cards?: boolean, cards_count?: number}) => {
      e.preventDefault();
      close();
      void (async () => {
        const items: { label: string; action: () => void | Promise<void> }[] = [
          {
            label: "Open",
            action: () => {
              navigate(`/notes/${note.note_id}`);
            },
          },
          {
            label: "Edit",
            action: () => {
              navigate(`/notes/${note.note_id}/update`);
            },
          },
        ];
        if (note.is_deleted) {
          items.push({
            label: "Restore",
            action: async () => {
              await restoreMut.mutateAsync(note.note_id);
            },
          });
        } else {
          items.push({
            label: "Delete",
            action: async () => {
              await deleteMut.mutateAsync(note.note_id);
            },
          });
        }
        items.push({
          label: "Add card",
          action: () => {
            navigate(`/cards/add?note_id=${note.note_id}&material_id=${note.material_id}`);
          },
        });
        if (note.has_cards) {
          items.push({
            label: `Open cards (${note.cards_count})`,
            action: () => {
              navigate(`/cards/?note_id=${encodeURIComponent(note.note_id)}`);
            },
          });
        }
        items.push({
          label: "Insert to repeat queue",
          action: async () => {
            try {
              await apiFetch(`/${encodeURIComponent(note.note_id)}/repeat-queue`, {
                method: "POST",
              });
            } catch (err) {
              console.error(err);
            }
          },
        });
        open(e.clientX, e.clientY, items);
      })();
    },
    [close, deleteMut, open, restoreMut],
  );

  const onQueryKeyDown = useCallback(async (e: React.KeyboardEvent<HTMLInputElement>) => {
    const v = e.currentTarget.value;
    if (!v.trim()) {
      return;
    }
    try {
      const r = await apiFetch<{ autocompletions: string[] }>(
        `/autocompletion${buildQuery({ query: v, limit: 5 })}`,
      );
      setHintList(r?.autocompletions ?? []);
    } catch {
      setHintList([]);
    }
  }, []);

  useEffect(() => {
    const root = notesRootRef.current;
    if (!root) {
      return;
    }
    const links = root.querySelectorAll("p.link-ref");
    const cleanups: (() => void)[] = [];
    for (const link of links) {
      const el = link as HTMLElement;
      const onEnter = async () => {
        const text = el.textContent ?? "";
        const linkId = text.replace(/\[\[/g, "").replace(/\]\]/g, "").trim();
        if (!linkId) {
          return;
        }
        const cacheKey = `link-ref-${linkId}`;
        const cached = localStorage.getItem(cacheKey);
        if (cached) {
          el.title = cached;
          return;
        }
        try {
          const note = await apiFetch<{ content: string }>(
            `/${linkId}`,
          );
          if (note?.content) {
            localStorage.setItem(cacheKey, note.content);
            el.title = note.content;
          }
        } catch {
          /* ignore */
        }
      };
      el.addEventListener("mouseenter", onEnter);
      cleanups.push(() => {
        el.removeEventListener("mouseenter", onEnter);
      });
    }
    return () => {
      for (const c of cleanups) {
        c();
      }
    };
  }, [searchData?.notes]);

  if (metaQ.isLoading) {
    return <p>Loading…</p>;
  }
  if (metaQ.error) {
    return <p className="error">{(metaQ.error as Error).message}</p>;
  }
  if (!hasTitles) {
    return (
      <div className="not-found">
        <p className="message"> No materials found </p>
      </div>
    );
  }

  if (searchQ.isLoading) {
    return <p>Loading…</p>;
  }
  if (searchQ.error) {
    return <PageLoadError pagination={pagination} error={searchQ.error} />;
  }

  const data = searchQ.data;
  if (!data) {
    return null;
  }

  const chaptersMenu = data.chapters;
  const materialTypes = data.material_types;
  const materialNotes = data.material_notes;

  return (
    <>
      <div className="form">
        <form
          key={`${materialId}|${query}|${tagsQuery}`}
          id="search-notes-form"
          action="#"
          method="get"
          onSubmit={(e) => {
            e.preventDefault();
            const fd = new FormData(e.currentTarget);
            const next = new URLSearchParams();
            const mid = String(fd.get("material_id") ?? "").trim();
            const q = String(fd.get("query") ?? "").trim();
            const tq = String(fd.get("tags_query") ?? "").trim();
            if (mid) {
              next.set("material_id", mid);
            }
            if (q) {
              next.set("query", q);
            }
            if (tq) {
              next.set("tags_query", tq);
            }
            setSearchParams(next);
          }}
        >
          <input
            className="input"
            list="books"
            name="material_id"
            defaultValue={materialId}
            placeholder="Choose a material"
          />
          <input
            id="search-hints"
            className="input"
            list="search-note-hints"
            name="query"
            defaultValue={query}
            placeholder="Enter a query"
            onKeyDown={onQueryKeyDown}
          />
          <datalist id="search-note-hints">
            {hintList.map((h) => (
              <option key={h} value={h} />
            ))}
          </datalist>
          <input
            className="input"
            list="tags"
            name="tags_query"
            defaultValue={tagsQuery}
            placeholder="Enter tags"
          />
          <datalist id="tags">
            {data.tags.map((tag) => (
              <option key={tag} value={tag}>
                {" "}
                #{tag}{" "}
              </option>
            ))}
          </datalist>
          <datalist id="books">
            {Object.entries(titles)
              .sort((a, b) => a[1].localeCompare(b[1]))
              .map(([id, title]) => (
                <option key={id} value={id}>
                  {" "}
                  «{title}»{" "}
                </option>
              ))}
          </datalist>
          <button type="submit" className="submit-button">
            {" "}
            Search{" "}
          </button>
        </form>
      </div>

      {Object.keys(chaptersMenu).length > 0 ? (
        <div className="menu">
          <details className="menu">
            <summary> Menu </summary>
            <div className="menu-items">
              {Object.entries(chaptersMenu)
                .sort(([a], [b]) => a.localeCompare(b))
                .map(([mid, chs]) => {
                  const mt = materialTypes[mid];
                  const chapterName =
                    mt === "course" ? "Block" : "Chapter";
                  return (
                    <div key={mid} className="material-link">
                      <details open className="chapters">
                        <summary>
                          {" "}
                          <a className="title-link" href={`#material-${mid}`}>
                            {" "}
                            «{data.titles[mid] ?? "Without material"}»{" "}
                          </a>{" "}
                        </summary>
                        <div className="chapters">
                          {chs.map((ch) => (
                            <a
                              key={ch}
                              className="chapter-link"
                              href={`#material-${mid}-chapter-${ch}`}
                            >
                              {" "}
                              {chapterName} {ch}{" "}
                            </a>
                          ))}
                        </div>
                      </details>
                    </div>
                  );
                })}
            </div>
          </details>
        </div>
      ) : null}

      <PageNav
        pagination={pagination}
        nextToken={data.next_token}
        isBusy={searchQ.isPlaceholderData}
      />
      {data.notes.length > 0 ? (
        <div ref={notesRootRef}>
          {grouped.map((group, gi) => {
            const mt = materialTypes[group.materialId];
            const { pageName, chapterName } = labelsForMaterialType(mt);
            const notesCount =
              materialNotes[group.materialId] ?? group.chapters.flatMap((c) => c.notes).length;
            return (
              <div key={group.materialId} className="group">
                {gi > 0 ? <hr className="material_divider" /> : null}
                <h3
                  className="material_title"
                  id={`material-${group.materialId}`}
                  onClick={() => {
                    navigate(`/materials/completed/${group.materialId}`);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      navigate(`/materials/completed/${group.materialId}`);
                    }
                  }}
                  role="presentation"
                  title="Click to open the material"
                >
                  {" "}
                  «{data.titles[group.materialId] ?? "Without material"}» ({notesCount}){" "}
                </h3>
                {group.chapters.map((ch) => (
                  <div key={`${group.materialId}-${ch.chapter}`}>
                    <h4
                      className="chapter_number"
                      id={`material-${group.materialId}-chapter-${ch.chapter}`}
                    >
                      {" "}
                      {chapterName}: {ch.chapter}{" "}
                    </h4>
                    {ch.notes.map((note) => {
                      const idx = indexByNoteId.get(note.note_id) ?? 0;
                      return (
                        <div
                          key={note.note_id}
                          className="note hover"
                          id={note.note_id}
                          onContextMenu={(e) => onNoteContextMenu(e, note)}
                        >
                          <p className="little-text">
                            {" "}
                            {idx} / {notesCount}{" "}
                          </p>
                          <p
                            className="little-text note-id-row hover"
                            role="presentation"
                            onClick={async () => {
                              const type = "text/plain";
                              const blob = new Blob([note.note_id], { type });
                              await navigator.clipboard.write([
                                new ClipboardItem({ [type]: blob }),
                              ]);
                            }}
                          >
                            {" "}
                            Note id: {note.note_id}{" "}
                          </p>
                          {note.title ? (
                            <p className="note-title large-text"> «{note.title}» </p>
                          ) : null}
                          <p
                            className="note-content"
                            dangerouslySetInnerHTML={{ __html: parseMarkdown(note.content_html) }}
                          />
                          {note.tags_html ? (
                            <p
                              className="note-content"
                              dangerouslySetInnerHTML={{ __html: note.tags_html }}
                            />
                          ) : null}
                          {note.link_html ? (
                            <p
                              className="note-content link-ref"
                              dangerouslySetInnerHTML={{ __html: note.link_html }}
                            />
                          ) : null}
                          <p className="note-page">
                            {" "}
                            {pageName}: {note.page}{" "}
                          </p>
                          <p className="medium-text" title="How many notes link to this one">
                            {" "}
                            Links count: {note.links_count}{" "}
                          </p>
                        </div>
                      );
                    })}
                  </div>
                ))}
              </div>
            );
          })}
        </div>
      ) : (
        <div className="not-found">
          <p className="message"> No notes found </p>
        </div>
      )}
      <PageNav
        pagination={pagination}
        nextToken={data.next_token}
        isBusy={searchQ.isPlaceholderData}
      />
      <ScrollArrows />
    </>
  );
}
