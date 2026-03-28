import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { apiFetch, buildQuery } from "../../api/notes";
import { useContextMenu } from "../../contexts/ContextMenuContext";

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
  current_page: number;
  page_size: number;
  material_id: string | null;
};

type MetaResponse = {
  titles: Record<string, string>;
  tags: string[];
};

type NoteJson = {
  note_id: string;
  material_id: string;
  is_deleted: boolean;
};

type HasCards = {
  has_cards: boolean;
  cards_count: number;
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

function buildPaginationItems(
  currentPage: number,
  maxPage: number,
): (number | "«" | "»")[] {
  const items: (number | "«" | "»")[] = [];
  let rangeStart = 1;
  let rangeStop = 11;
  if (currentPage > 5) {
    rangeStart = currentPage - 4;
    rangeStop = currentPage + 6;
    items.push("«");
  }
  for (let p = rangeStart; p < rangeStop && p <= maxPage; p++) {
    if (p >= 1) {
      items.push(p);
    }
  }
  items.push("»");
  return items;
}

async function fetchNoteJson(noteId: string): Promise<NoteJson> {
  const r = await apiFetch<NoteJson>(`/note-json${buildQuery({ note_id: noteId })}`);
  if (!r) {
    throw new Error("Empty note response");
  }
  return r;
}

async function fetchHasCards(noteId: string): Promise<HasCards> {
  const res = await fetch(`/cards/has-cards?note_id=${encodeURIComponent(noteId)}`, {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
  });
  const text = await res.text();
  if (!res.ok) {
    throw new Error(text.slice(0, 200) || `HTTP ${res.status}`);
  }
  return JSON.parse(text) as HasCards;
}

export function SearchNotesPage() {
  const qc = useQueryClient();
  const { open, close } = useContextMenu();
  const [searchParams, setSearchParams] = useSearchParams();
  const notesRootRef = useRef<HTMLDivElement>(null);

  const materialId = searchParams.get("material_id") ?? "";
  const query = searchParams.get("query") ?? "";
  const tagsQuery = searchParams.get("tags_query") ?? "";
  const pageParam = searchParams.get("page");
  const currentPage = Math.max(1, parseInt(pageParam ?? "1", 10) || 1);

  const [hintList, setHintList] = useState<string[]>([]);

  const metaQ = useQuery({
    queryKey: ["notes", "meta", materialId],
    queryFn: () =>
      apiFetch<MetaResponse>(`/meta${buildQuery({ material_id: materialId || undefined })}`),
  });

  const searchQ = useQuery({
    queryKey: ["notes", "search", materialId, query, tagsQuery, currentPage],
    queryFn: () =>
      apiFetch<SearchResponse>(
        `/search${buildQuery({
          material_id: materialId || undefined,
          query: query || undefined,
          tags_query: tagsQuery || undefined,
          page: currentPage,
          page_size: PAGE_SIZE,
        })}`,
      ),
  });

  const titles = metaQ.data?.titles ?? {};
  const hasTitles = Object.keys(titles).length > 0;

  const searchData = searchQ.data;
  const totalCount = searchData?.total_count ?? 0;
  const maxPage = Math.max(1, Math.ceil(totalCount / PAGE_SIZE));

  const grouped = useMemo(
    () => (searchData?.notes ? groupNotesByMaterialAndChapter(searchData.notes) : []),
    [searchData?.notes],
  );

  const indexByNoteId = useMemo(() => {
    const m = new Map<string, number>();
    if (!searchData) {
      return m;
    }
    let i = (searchData.current_page - 1) * searchData.page_size;
    for (const g of grouped) {
      for (const ch of g.chapters) {
        for (const n of ch.notes) {
          i += 1;
          m.set(n.note_id, i);
        }
      }
    }
    return m;
  }, [grouped, searchData]);

  const setPage = useCallback(
    (p: number) => {
      const next = new URLSearchParams(searchParams);
      if (p <= 1) {
        next.delete("page");
      } else {
        next.set("page", String(p));
      }
      setSearchParams(next);
    },
    [searchParams, setSearchParams],
  );

  const onPaginationClick = useCallback(
    (item: number | "«" | "»") => {
      const cp = searchData?.current_page ?? currentPage;
      if (item === "«") {
        setPage(Math.max(1, cp - 1));
      } else if (item === "»") {
        setPage(Math.min(maxPage, cp + 1));
      } else {
        setPage(item);
      }
    },
    [currentPage, maxPage, searchData?.current_page, setPage],
  );

  const deleteMut = useMutation({
    mutationFn: async (noteId: string) => {
      const res = await fetch("/notes/delete", {
        method: "DELETE",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ note_id: noteId }),
      });
      if (!res.ok) {
        const t = await res.text();
        throw new Error(t.slice(0, 200) || `HTTP ${res.status}`);
      }
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["notes"] });
    },
  });

  const restoreMut = useMutation({
    mutationFn: async (noteId: string) => {
      const res = await fetch("/notes/restore", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ note_id: noteId }),
      });
      if (!res.ok) {
        const t = await res.text();
        throw new Error(t.slice(0, 200) || `HTTP ${res.status}`);
      }
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["notes"] });
    },
  });

  const onNoteContextMenu = useCallback(
    (e: React.MouseEvent, noteId: string) => {
      e.preventDefault();
      close();
      void (async () => {
        let noteJson: NoteJson;
        try {
          noteJson = await fetchNoteJson(noteId);
        } catch {
          return;
        }
        let hasCards: HasCards = { has_cards: false, cards_count: 0 };
        try {
          hasCards = await fetchHasCards(noteId);
        } catch {
          /* ignore */
        }
        const items: { label: string; action: () => void | Promise<void> }[] = [
          {
            label: "Open",
            action: () => {
              window.open(`/notes/note?note_id=${noteId}`);
            },
          },
          {
            label: "Edit",
            action: () => {
              window.open(`/notes/update-view?note_id=${noteId}`);
            },
          },
        ];
        if (noteJson.is_deleted) {
          items.push({
            label: "Restore",
            action: async () => {
              await restoreMut.mutateAsync(noteId);
            },
          });
        } else {
          items.push({
            label: "Delete",
            action: async () => {
              await deleteMut.mutateAsync(noteId);
            },
          });
        }
        items.push({
          label: "Add card",
          action: () => {
            window.open(
              `/cards/add-view?note_id=${noteId}&material_id=${noteJson.material_id}`,
            );
          },
        });
        if (hasCards.has_cards) {
          items.push({
            label: `Open cards (${hasCards.cards_count})`,
            action: () => {
              window.open(`/cards/list?note_id=${noteId}`);
            },
          });
        }
        items.push({
          label: "Insert to repeat queue",
          action: async () => {
            const res = await fetch(
              `/notes/repeat-queue/insert?note_id=${encodeURIComponent(noteId)}`,
              {
                method: "POST",
                credentials: "same-origin",
                headers: { "Content-Type": "application/json" },
              },
            );
            if (!res.ok) {
              console.error(await res.text());
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
            `/note-json${buildQuery({ note_id: linkId })}`,
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
    return <p className="error">{(searchQ.error as Error).message}</p>;
  }

  const data = searchQ.data;
  if (!data) {
    return null;
  }

  const chaptersMenu = data.chapters;
  const materialTypes = data.material_types;
  const materialNotes = data.material_notes;
  const paginationItems = buildPaginationItems(data.current_page, maxPage);

  return (
    <>
      <div className="form">
        <form
          key={`${materialId}|${query}|${tagsQuery}|${currentPage}`}
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

      <div className="form pagination">
        {paginationItems.map((item, i) => {
          const key = `${item}-${i}`;
          if (item === "«" || item === "»") {
            return (
              <div
                key={key}
                className="pagination-item hover"
                role="presentation"
                onClick={() => {
                  onPaginationClick(item);
                }}
              >
                {" "}
                {item}{" "}
              </div>
            );
          }
          return (
            <div
              key={key}
              className={`pagination-item hover ${item === data.current_page ? "current-page" : ""}`}
              role="presentation"
              onClick={() => {
                onPaginationClick(item);
              }}
            >
              {item}
            </div>
          );
        })}
      </div>

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
                    window.open(`/materials/completed#${group.materialId}`, "_blank");
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      window.open(`/materials/completed#${group.materialId}`, "_blank");
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
                          onContextMenu={(e) => onNoteContextMenu(e, note.note_id)}
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
                            dangerouslySetInnerHTML={{ __html: note.content_html }}
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
    </>
  );
}
