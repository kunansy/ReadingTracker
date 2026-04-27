import {useMutation, useQuery, useQueryClient} from "@tanstack/react-query";
import {useRef, useState} from "react";

import {apiFetch} from "../../api/materials";
import {useAltchHotkeys} from "../../hooks/useAltchHotkeys";
import {ComboboxInput, ComboboxList, ComboboxRoot} from "../../components/Combobox";
import {
  MaterialType,
  MaterialTagsResponse,
  MaterialTypes,
  MaterialAuthorsResponse,
  ParsedMaterialResponse,
} from "../../types";


export function AddMaterialPage() {
  const titleRef = useRef<HTMLInputElement>(null);
  useAltchHotkeys(titleRef);

  const [title, setTitle] = useState("");
  const [authors, setAuthors] = useState("");
  const [pages, setPages] = useState("");
  const [materialType, setMaterialType] = useState<MaterialType | null>(null);
  const [tags, setTags] = useState<string[]>([]);
  const [link, setLink] = useState("");
  const [parseUrl, setParseUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const qc = useQueryClient();

  const materialTagsQ = useQuery({
    queryKey: ["materials", "tags"],
    queryFn: () => apiFetch<MaterialTagsResponse>(`/tags`),
    staleTime: 5 * 60 * 1000,
  });
  const materialAuthorsQ = useQuery({
    queryKey: ["materials", "authors"],
    queryFn: () => apiFetch<MaterialAuthorsResponse>(`/authors`),
    staleTime: 5 * 60 * 1000,
  });

  const parseMut = useMutation({
    mutationFn: async (url: string) => {
      const endpoint = url.includes("habr")
        ? "/parse/habr"
        : "/parse/youtube";
      return apiFetch<ParsedMaterialResponse>(endpoint, {
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
      setMaterialType(null);
      setTags([]);
      setLink("");
      setParseUrl("");
      setError(null);

      void qc.invalidateQueries({ queryKey: ["materials", "queue"], });
      // todo: invalidate if new ones added only
      void qc.invalidateQueries({ queryKey: ["materials", "tags"], });
      void qc.invalidateQueries({ queryKey: ["materials", "authors"], });
    },
    onError: (e: Error) => {
      setError(e.message);
    },
  });


  if (materialTagsQ.isLoading || materialAuthorsQ.isLoading) {
    return <p>Loading…</p>;
  }
  const err = materialTagsQ.error || materialAuthorsQ.error;
  if (err) {
    return <p className="error">{(err as Error).message}</p>;
  }

  const materialTags = materialTagsQ.data?.tags ?? [];
  const materialAuthors = materialAuthorsQ.data?.authors ?? [];

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
                options={materialAuthors}
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
                value={materialType ?? ""}
                onChange={setMaterialType}
                options={MaterialTypes ?? []}
            >
              <ComboboxInput placeholder="Enter a material type" />
              <ComboboxList />
            </ComboboxRoot>

            <ComboboxRoot
                value={tags}
                onChange={setTags}
                options={materialTags}
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
