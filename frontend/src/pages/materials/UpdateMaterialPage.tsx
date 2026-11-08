import {useMutation, useQueryClient} from "@tanstack/react-query";
import {useEffect, useRef, useState} from "react";
import {useLocation, useNavigate, useSearchParams} from "react-router-dom";

import { api, unwrapEmpty } from "../../api/client";
import {
  type GetMaterialResponse,
  type MaterialTypesEnum,
  materialTypesEnumValues,
  type UpdateMaterialRequest,
} from "../../api/schema";
import {useAltchHotkeys} from "../../hooks/useAltchHotkeys";
import { isMaterialType } from "../../types";
import {ComboboxInput, ComboboxList, ComboboxRoot} from "../../components/Combobox";
import { materialKeys, useMaterial, useMaterialTags } from "../../materials/queries";

export function UpdateMaterialPage() {
  const [searchParams] = useSearchParams();
  const materialId = searchParams.get("material_id");
  const titleRef = useRef<HTMLInputElement>(null);

  const [title, setTitle] = useState("");
  useAltchHotkeys(titleRef, title, setTitle);
  const [authors, setAuthors] = useState("");
  const [pages, setPages] = useState("");
  const [materialType, setMaterialType] = useState<MaterialTypesEnum>("book");
  const [tags, setTags] = useState<string[]>([]);
  const [link, setLink] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const qc = useQueryClient();
  const location = useLocation();
  const navigate = useNavigate();

  const from = location.state?.from || "/materials/queue";

  const q = useMaterial(materialId);
  const materialTagsQ = useMaterialTags();

  useEffect(() => {
    const m = q.data?.material;
    if (!m) {
      return;
    }
    setTitle(m.title);
    setAuthors(m.authors);
    setPages(String(m.pages));
    setMaterialType(m.material_type);
    setTags(m.tags ? m.tags.split(", ") : []);
    setLink(m.link ?? "");
  }, [q.data, materialId]);

  const updateMut = useMutation({
    mutationFn: async () => {
      if (!materialId) {
        throw new Error("Missing material_id");
      }
      const body: UpdateMaterialRequest = {
        material_id: materialId,
        title,
        authors,
        pages: Number(pages),
        material_type: materialType,
        tags: tags.join(", "),
        link: link.trim() || null,
      };
      await unwrapEmpty(
        api.PATCH("/api/v1/materials/{material_id}", {
          params: { path: { material_id: materialId } },
          body,
        }),
      );
    },
    onSuccess: () => {
      setMessage("Material updated successfully.");
      setError(null);

      qc.setQueryData<GetMaterialResponse>(materialKeys.byId(materialId ?? ""), (old) => {
        if (!old) return old;

        return {
          ...old,
          material: {
            ...old.material,
            title,
            authors,
            pages: Number(pages),
            material_type: materialType,
            tags: tags.join(", "),
            link: link.trim() || null,
          },
        };
      });

      void qc.invalidateQueries({ queryKey: materialKeys.all });
      navigate(from);
    },
  });

  if (!materialId) {
    return <p className="error">Missing material_id</p>;
  }

  if (q.isLoading || materialTagsQ.isLoading) {
    return <p>Loading…</p>;
  }
  const err = q.error || materialTagsQ.error;
  if (err) {
    return <p className="error">{err.message}</p>;
  }

  const materialTags = materialTagsQ.data?.tags ?? [];

  return (
    <>
      {message ? <div className="alert success">{message}</div> : null}
      {error ? <div className="alert error">{error}</div> : null}
      <div className="form">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            updateMut.mutate();
          }}
        >
          <fieldset className="fieldset">
            <legend className="legend"> Update a material </legend>
            <input
              ref={titleRef}
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
              className="input"
              type="text"
              placeholder="Enter authors"
              name="authors"
              value={authors}
              title="Authors of the material"
              onChange={(e) => {
                setAuthors(e.target.value);
              }}
            />
            <input
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
                onChange={(value) => {
                  if (isMaterialType(value)) {
                    setMaterialType(value);
                  }
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
              Update
            </button>
          </fieldset>
        </form>
      </div>
    </>
  );
}
