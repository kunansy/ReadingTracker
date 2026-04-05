import {useMutation, useQuery, useQueryClient} from "@tanstack/react-query";
import {useEffect, useRef, useState} from "react";
import {useLocation, useNavigate, useSearchParams} from "react-router-dom";

import {apiFetch} from "../../api/materials";
import {useAltchHotkeys} from "../../hooks/useAltchHotkeys";
import {MaterialJson, MaterialTagsResponse, MaterialType, MaterialTypes} from "../../types";
import {ComboboxInput, ComboboxList, ComboboxRoot} from "../../components/Combobox";

type MaterialResponse = {
  material: MaterialJson;
};

export function UpdateMaterialPage() {
  const [searchParams] = useSearchParams();
  const materialId = searchParams.get("material_id");
  const titleRef = useRef<HTMLInputElement>(null);
  useAltchHotkeys(titleRef);

  const [materialTags, setMaterialTags] = useState<MaterialTagsResponse | null>(null);
  const [title, setTitle] = useState("");
  const [authors, setAuthors] = useState("");
  const [pages, setPages] = useState("");
  const [materialType, setMaterialType] = useState<MaterialType>(MaterialType.book);
  const [tags, setTags] = useState<string[]>([]);
  const [link, setLink] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const qc = useQueryClient();
  const location = useLocation();
  const navigate = useNavigate();

  const from = location.state?.from || "/materials/queue";

  useEffect(() => {
    void apiFetch<MaterialTagsResponse>("/tags").then(setMaterialTags).catch(() => {
      setError("Failed to load material tags");
    });
  }, []);

  const q = useQuery({
    queryKey: ["material", materialId],
    enabled: Boolean(materialId),
    queryFn: () => apiFetch<MaterialResponse>(`/${materialId}`),
  });

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
      const body: Record<string, unknown> = {
        material_id: materialId,
        title,
        authors,
        pages: Number(pages),
        material_type: materialType,
        tags: tags.join(", "),
        link: link.trim() || null,
      };
      await apiFetch(`/${materialId}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      });
    },
    onSuccess: () => {
      setMessage("Material updated successfully.");
      setError(null);

      qc.setQueryData(["material", materialId], (old: any) => {
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

      void qc.invalidateQueries({ queryKey: ["materials"] });
      navigate(from);
    },
  });

  if (!materialId) {
    return <p className="error">Missing material_id</p>;
  }

  if (q.isLoading) {
    return <p>Loading…</p>;
  }
  if (q.error) {
    return <p className="error">{(q.error as Error).message}</p>;
  }

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
          <fieldset className="material-fieldset">
            <legend className="material-legend"> Update a material </legend>
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
