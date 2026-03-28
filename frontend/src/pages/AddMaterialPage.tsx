import { useMutation } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { apiFetch } from "../api/materials";
import { useAltchHotkeys } from "../hooks/useAltchHotkeys";
import type { MaterialType } from "../types";

type MetaResponse = {
  tags_list: string[];
  material_authors: string[];
  material_types: string[];
};

type ParsedMaterial = {
  title: string;
  authors: string;
  type: string;
  link: string;
  duration?: number | null;
};

export function AddMaterialPage() {
  const titleRef = useRef<HTMLInputElement>(null);
  useAltchHotkeys(titleRef);

  const [meta, setMeta] = useState<MetaResponse | null>(null);
  const [title, setTitle] = useState("");
  const [authors, setAuthors] = useState("");
  const [pages, setPages] = useState("");
  const [materialType, setMaterialType] = useState<MaterialType>("book");
  const [tags, setTags] = useState("");
  const [link, setLink] = useState("");
  const [parseUrl, setParseUrl] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void apiFetch<MetaResponse>("/meta").then(setMeta).catch(() => {
      setError("Failed to load form metadata");
    });
  }, []);

  const parseMut = useMutation({
    mutationFn: async (url: string) => {
      const endpoint = url.includes("habr")
        ? "/parse/habr"
        : "/parse/youtube";
      return apiFetch<ParsedMaterial>(endpoint, {
        method: "POST",
        body: JSON.stringify({ link: url }),
      });
    },
    onSuccess: (data) => {
      if (!data) {
        return;
      }
      setTitle(data.title);
      setAuthors(data.authors);
      if (data.duration != null) {
        setPages(String(data.duration));
      }
      setMaterialType((data.type as MaterialType) ?? "book");
      setLink(data.link);
    },
    onError: (e: Error) => {
      setError(e.message);
    },
  });

  const addMut = useMutation({
    mutationFn: async () => {
      const body: Record<string, unknown> = {
        title,
        authors,
        pages: Number(pages),
        material_type: materialType,
      };
      if (tags.trim()) {
        body.tags = tags.trim();
      }
      if (link.trim()) {
        body.link = link.trim();
      }
      await apiFetch("/", {
        method: "POST",
        body: JSON.stringify(body),
      });
    },
    onSuccess: () => {
      setTitle("");
      setAuthors("");
      setPages("");
      setMaterialType("book");
      setTags("");
      setLink("");
      setError(null);
    },
    onError: (e: Error) => {
      setError(e.message);
    },
  });

  return (
    <>
      <div className="parse-material-source">
        <fieldset className="material-fieldset">
          <legend className="material-legend"> Parse youtube or habr </legend>
          <input
            id="parse-url"
            className="input"
            type="url"
            placeholder="Habr or youtube url"
            value={parseUrl}
            onChange={(e) => {
              setParseUrl(e.target.value);
            }}
          />
          <button
            id="parse-btn"
            type="button"
            className="submit-button"
            onClick={() => {
              setError(null);
              if (!parseUrl.trim()) {
                return;
              }
              parseMut.mutate(parseUrl.trim());
            }}
          >
            Parse
          </button>
        </fieldset>
      </div>

      <div className="form">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setError(null);
            addMut.mutate();
          }}
        >
          <fieldset className="material-fieldset">
            <legend className="material-legend"> Add a material </legend>
            <input
              ref={titleRef}
              id="input-title"
              className="input altch"
              type="text"
              placeholder="Enter a title"
              name="title"
              value={title}
              title="Title of the material"
              onChange={(e) => {
                setTitle(e.target.value);
              }}
            />
            <input
              id="input-authors"
              className="input"
              type="text"
              list="material_authors"
              placeholder="Enter authors"
              name="authors"
              value={authors}
              title="Authors of the material"
              onChange={(e) => {
                setAuthors(e.target.value);
              }}
            />
            <datalist id="material_authors">
              {(meta?.material_authors ?? []).map((a) => (
                <option key={a} value={a}>
                  «{a}»
                </option>
              ))}
            </datalist>
            <input
              id="input-duration"
              className="input"
              type="number"
              placeholder="Enter a count of pages"
              name="pages"
              value={pages}
              title="Count of pages in the materials"
              onChange={(e) => {
                setPages(e.target.value);
              }}
            />
            <input
              id="input-type"
              className="input"
              type="text"
              list="material_types"
              placeholder="Enter material type"
              name="material_type"
              value={materialType}
              title="Type of the material"
              onChange={(e) => {
                setMaterialType(e.target.value as MaterialType);
              }}
            />
            <datalist id="material_types">
              {(meta?.material_types ?? []).map((t) => (
                <option key={t} value={t}>
                  «{t}»
                </option>
              ))}
            </datalist>
            <input
              id="input-tags"
              className="input"
              type="text"
              list="tags"
              placeholder="Enter tags"
              name="tags"
              value={tags}
              title="Tags of the material"
              onChange={(e) => {
                setTags(e.target.value);
              }}
            />
            <datalist id="tags">
              {(meta?.tags_list ?? []).map((t) => (
                <option key={t} value={t}>
                  «{t}»
                </option>
              ))}
            </datalist>
            <input
              id="input-link"
              className="input"
              type="text"
              placeholder="Enter link"
              name="link"
              value={link}
              title="Link to the material"
              onChange={(e) => {
                setLink(e.target.value);
              }}
            />
            <button type="submit" className="submit-button">
              Add
            </button>
          </fieldset>
        </form>
      </div>
      {error ? <p className="error">{error}</p> : null}
    </>
  );
}
