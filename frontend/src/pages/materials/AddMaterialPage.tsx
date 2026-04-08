import {useMutation, useQueryClient} from "@tanstack/react-query";
import {useEffect, useRef, useState} from "react";

import {apiFetch} from "../../api/materials";
import {useAltchHotkeys} from "../../hooks/useAltchHotkeys";
import {ComboboxInput, ComboboxList, ComboboxRoot} from "../../components/Combobox";
import {
  MaterialType,
  MaterialTagsResponse,
  MaterialTypes,
  MaterialAuthorsResponse,
} from "../../types";


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

  const [materialTags, setMaterialTags] = useState<MaterialTagsResponse | null>(null);
  const [materialAuthors, setMaterialAuthors] = useState<MaterialAuthorsResponse | null>(null);
  const [title, setTitle] = useState("");
  const [authors, setAuthors] = useState("");
  const [pages, setPages] = useState("");
  const [materialType, setMaterialType] = useState<MaterialType>(MaterialType.book);
  const [tags, setTags] = useState<string[]>([]);
  const [link, setLink] = useState("");
  const [parseUrl, setParseUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const qc = useQueryClient();

  useEffect(() => {
    void apiFetch<MaterialTagsResponse>("/tags").then(setMaterialTags).catch(() => {
      setError("Failed to load material tags");
    });
  }, []);
  useEffect(() => {
    void apiFetch<MaterialAuthorsResponse>("/authors").then(setMaterialAuthors).catch(() => {
      setError("Failed to load material authors");
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
      setMaterialType((data.type as MaterialType) ?? MaterialType.book);
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
      if (tags.length) {
        body.tags = tags.join(", ");
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
      setMaterialType(MaterialType.book);
      setTags([]);
      setLink("");
      setError(null);

      void qc.invalidateQueries({ queryKey: ["queue"] });
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

            <ComboboxRoot
                value={authors}
                onChange={setAuthors}
                options={materialAuthors?.authorsList ?? []}
                allowCreate
            >
              <ComboboxInput placeholder="Enter a material authors" />
              <ComboboxList />
            </ComboboxRoot>

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

            <ComboboxRoot
                value={materialType}
                onChange={setMaterialType}
                options={MaterialTypes ?? []}
            >
              <ComboboxInput placeholder="Enter a material type" />
              <ComboboxList />
            </ComboboxRoot>

            <ComboboxRoot
                value={tags}
                onChange={setTags}
                options={materialTags?.tagsList ?? []}
                multiple
                allowCreate
            >
              <ComboboxInput placeholder="Enter tags" />
              <ComboboxList />
            </ComboboxRoot>

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
