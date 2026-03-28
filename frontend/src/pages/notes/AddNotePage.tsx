import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { apiFetch, buildQuery } from "../../api/notes";
import { CelebrateButton } from "../../components/CelebrateButton";
import { useAltchHotkeys } from "../../hooks/useAltchHotkeys";

type MetaResponse = {
  titles: Record<string, string>;
  tags: string[];
};

function isUuid(value: string): boolean {
  return /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/.test(
    value.trim(),
  );
}

export function AddNotePage() {
  const [searchParams] = useSearchParams();
  const initialMaterial = searchParams.get("material_id") ?? "";

  const contentRef = useRef<HTMLTextAreaElement>(null);
  useAltchHotkeys(contentRef);

  const [materialId, setMaterialId] = useState(initialMaterial);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [tags, setTags] = useState("");
  const [linkId, setLinkId] = useState("");
  const [chapter, setChapter] = useState("");
  const [page, setPage] = useState("");
  const [tagList, setTagList] = useState<string[]>([]);
  const [successId, setSuccessId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const metaQ = useQuery({
    queryKey: ["notes", "meta", materialId],
    queryFn: () =>
      apiFetch<MetaResponse>(`/meta${buildQuery({ material_id: materialId || undefined })}`),
  });

  useEffect(() => {
    if (!materialId || !isUuid(materialId)) {
      setTagList([]);
      return;
    }
    void apiFetch<{ tags: string[] }>(
      `/tags${buildQuery({ material_id: materialId })}`,
    )
      .then((r) => {
        setTagList(r?.tags ?? []);
      })
      .catch(() => {
        setTagList([]);
      });
  }, [materialId]);

  const addMut = useMutation({
    mutationFn: async () => {
      if (!isUuid(materialId)) {
        throw new Error("Choose a valid material (UUID)");
      }
      const body: Record<string, unknown> = {
        material_id: materialId,
        content,
        chapter: chapter || "",
        page: page === "" ? 0 : Number(page),
      };
      if (title.trim()) {
        body.title = title.trim();
      }
      if (tags.trim()) {
        body.tags = tags;
      }
      if (linkId.trim() && isUuid(linkId.trim())) {
        body.link_id = linkId.trim();
      }
      return apiFetch<{ ok: boolean; note_id: string }>("/add", {
        method: "POST",
        body: JSON.stringify(body),
      });
    },
    onSuccess: (data) => {
      setSuccessId(data?.note_id ?? null);
      setError(null);
      setTitle("");
      setContent("");
      setTags("");
      setLinkId("");
      setChapter("");
      setPage("");
    },
    onError: (e: Error) => {
      setError(e.message);
    },
  });

  const titles = metaQ.data?.titles ?? {};
  const hasTitles = Object.keys(titles).length > 0;

  useEffect(() => {
    const el = contentRef.current;
    if (!el) {
      return;
    }
    const onKeyUp = async (e: KeyboardEvent) => {
      const target = e.target as HTMLTextAreaElement;
      await new Promise((r) => {
        setTimeout(r, 2);
      });
      const text = target.value;
      try {
        const resp = await fetch(
          `https://speller.yandex.net/services/spellservice.json/checkText?text=${encodeURIComponent(text)}`,
        );
        const errata = (await resp.json()) as {
          word?: string;
          s?: string[];
        }[];
        const alertEl = document.getElementById("input-content-errata");
        if (!alertEl) {
          return;
        }
        if (!errata.length) {
          alertEl.innerHTML = "";
          return;
        }
        let img = alertEl.querySelector("#input-content-errata-img");
        if (!img) {
          img = document.createElement("img");
          img.id = "input-content-errata-img";
          (img as HTMLImageElement).src = "/static/errata-alert.png";
          alertEl.appendChild(img);
        }
        alertEl.title = errata
          .map((x) => `${x.word ?? ""} – ${(x.s ?? []).join(", ")}`)
          .join("\n");
      } catch {
        /* ignore */
      }
    };
    el.addEventListener("keyup", onKeyUp);
    return () => {
      el.removeEventListener("keyup", onKeyUp);
    };
  }, []);

  const pageLabel = "page number";
  const chapterLabel = "chapter";

  if (!metaQ.isLoading && !hasTitles) {
    return (
      <div className="not-found">
        <p className="message"> No materials found </p>
      </div>
    );
  }

  return (
    <>
      {successId ? (
        <div className="alert success hover add-note-alert" id={successId}>
          Note &apos;{successId}&apos; successfully inserted.
        </div>
      ) : null}
      <div className="form">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setError(null);
            addMut.mutate();
          }}
        >
          <fieldset className="add-note-fieldset">
            <legend className="add-note-legend"> Add note </legend>
            <input
              id="input_material_id"
              className="input input-datalist"
              list="books"
              placeholder="Choose a material"
              value={materialId}
              title="ID of the material"
              onChange={(e) => {
                setMaterialId(e.target.value);
              }}
            />
            <datalist id="books">
              {Object.entries(titles)
                .sort((a, b) => a[1].localeCompare(b[1]))
                .map(([id, t]) => (
                  <option key={id} value={id}>
                    «{t}»
                  </option>
                ))}
            </datalist>
            <input
              className="input"
              placeholder="Enter a title"
              value={title}
              title="Title of the note"
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
              title="Text of the note"
              onChange={(e) => {
                setContent(e.target.value);
              }}
            />
            <div id="input-content-errata" />
            <input
              id="note-tags"
              className="input"
              list="tags"
              placeholder="Enter tags"
              value={tags}
              title="Tags for the note"
              onChange={(e) => {
                setTags(e.target.value);
              }}
            />
            <datalist id="tags">
              {tagList.map((tag) => (
                <option key={tag} value={`#${tag}`}>
                  {tag}
                </option>
              ))}
            </datalist>
            <input
              id="note-link"
              className="input"
              placeholder="Enter a link"
              value={linkId}
              title="Link to the other note"
              onChange={(e) => {
                setLinkId(e.target.value);
              }}
            />
            <input
              className="input"
              placeholder={`Enter a ${chapterLabel}`}
              value={chapter}
              title={`${chapterLabel} where the note might be found`}
              onChange={(e) => {
                setChapter(e.target.value);
              }}
            />
            <input
              className="input"
              type="number"
              placeholder={`Enter a ${pageLabel}`}
              value={page}
              title={`${pageLabel} where the note might be found`}
              onChange={(e) => {
                setPage(e.target.value);
              }}
            />
            <CelebrateButton type="submit" className="submit-button">
              Add
            </CelebrateButton>
          </fieldset>
        </form>
      </div>
      {tagList.length > 0 ? (
        <ul id="tags-list" className="tags-list" title="Note tags">
          {tagList.map((tag) => (
            <li
              key={tag}
              value={tag}
              onClick={() => {
                const t = `#${tag}`;
                setTags((prev) => (prev.length === 0 ? t : `${prev} ${t}`));
              }}
            >
              #{tag}
            </li>
          ))}
        </ul>
      ) : null}
      {error ? <p className="error">{error}</p> : null}
    </>
  );
}
