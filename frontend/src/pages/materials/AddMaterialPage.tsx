import {useMutation, useQueryClient} from "@tanstack/react-query";
import {useState} from "react";

import { api, unwrap } from "../../api/client";
import { type CreateMaterialRequest, type MaterialTypesEnum, materialTypesEnumValues } from "../../api/schema";
import {ComboboxInput, ComboboxList, ComboboxRoot} from "../../components/Combobox";
import { isMaterialType } from "../../types";
import {CelebrateButton} from "../../components/CelebrateButton.tsx";
import { materialKeys, useMaterialAuthors, useMaterialTags } from "../../materials/queries";


export function AddMaterialPage() {
  const [title, setTitle] = useState("");
  const [authors, setAuthors] = useState<string[]>([]);
  const [pages, setPages] = useState("");
  const [materialType, setMaterialType] = useState<MaterialTypesEnum | null>(null);
  const [tags, setTags] = useState<string[]>([]);
  const [link, setLink] = useState("");
  const [parseUrl, setParseUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const qc = useQueryClient();

  const materialTagsQ = useMaterialTags();
  const materialAuthorsQ = useMaterialAuthors();

  const parseMut = useMutation({
    mutationFn: async (url: string) => {
      const endpoint = url.includes("habr")
        ? "/api/v1/materials/parse/habr"
        : "/api/v1/materials/parse/youtube";
      return unwrap(api.POST(endpoint, { body: { link: url } }));
    },
    onSuccess: (data) => {
      setTitle(data.title);
      setAuthors([data.authors]);
      if (data.duration != null) {
        setPages(String(data.duration));
      }
      setMaterialType(isMaterialType(data.type) ? data.type : "book");
      setLink(data.link);
    },
    onError: (e: Error) => {
      setError(e.message);
    },
  });

  const addMut = useMutation({
    mutationFn: async () => {
      if (materialType === null) {
        throw new Error("Choose the material type");
      }
      const body: CreateMaterialRequest = {
        title,
        authors: authors.join(", "),
        pages: Number(pages),
        material_type: materialType,
        tags: tags.length ? tags.join(", ") : undefined,
        link: link.trim() || undefined,
      };
      await unwrap(api.POST("/api/v1/materials/", { body }));
    },
    onSuccess: () => {
      setTitle("");
      setAuthors([]);
      setPages("");
      setMaterialType(null);
      setTags([]);
      setLink("");
      setParseUrl("");
      setError(null);

      void qc.invalidateQueries({ queryKey: materialKeys.queue });
      // todo: invalidate if new ones added only
      void qc.invalidateQueries({ queryKey: materialKeys.tags });
      void qc.invalidateQueries({ queryKey: materialKeys.authors });
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
    return <p className="error">{err.message}</p>;
  }

  const materialTags = materialTagsQ.data?.tags ?? [];
  const materialAuthors = materialAuthorsQ.data?.authors ?? [];

  return (
    <>
      <div className="parse-material-source">
        <fieldset className="fieldset">
          <legend className="legend"> Parse youtube or habr </legend>
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
          <fieldset className="fieldset">
            <legend className="legend"> Add a material </legend>
            <input
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
                multiple
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
                onChange={(v) => {
                  setMaterialType(isMaterialType(v) ? v : null);
                }}
                options={materialTypesEnumValues}
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
            <CelebrateButton
                type="submit"
                className="submit-button"
                disabled={addMut.isPending}
            >
              {addMut.isPending ? "Pending..." : "Add"}
            </CelebrateButton>
          </fieldset>
        </form>
      </div>
      {error ? <p className="error">{error}</p> : null}
    </>
  );
}
