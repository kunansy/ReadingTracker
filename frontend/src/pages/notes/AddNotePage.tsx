import { useMutation, useQuery } from "@tanstack/react-query";
import {useRef, useState, useCallback, useMemo} from "react";
import { useSearchParams } from "react-router-dom";

import { apiFetch, buildQuery } from "../../api/notes";
import { apiFetch as materialsApiFetch } from "../../api/materials";
import { CelebrateButton } from "../../components/CelebrateButton";
import { useAltchHotkeys } from "../../hooks/useAltchHotkeys";
import { ComboboxInput, ComboboxList, ComboboxRoot } from "../../components/Combobox.tsx";
import { ListMaterialsTitlesResponse, AddNoteRequest } from "../../types.ts";
import { useSpellChecker } from "../../hooks/useSpellChecker.ts";
import { SpellErrorsList } from "../../components/SpellErrorsList.tsx";
import {isUuid} from "../../utils/isUuid.ts";


export function AddNotePage() {
  const [searchParams] = useSearchParams();
  const initialMaterial = searchParams.get("material_id") ?? "";

  const contentRef = useRef<HTMLTextAreaElement>(null);
  useAltchHotkeys(contentRef);

  const [formData, setFormData] = useState<AddNoteRequest>({
    materialId: initialMaterial,
    title: "",
    content: "",
    tags: [],
    linkId: "",
    chapter: "",
    page: 0,
  });
  const [successId, setSuccessId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const { spellErrors, replaceWord } = useSpellChecker(
      formData.content,
      (newContent) => updateFormData({ content: newContent })
  );

  const titlesQ = useQuery({
    queryKey: ["materials", "titles"],
    queryFn: () => materialsApiFetch<ListMaterialsTitlesResponse>(`/titles`),
  });

  const tagListQ = useQuery({
    queryKey: ["tags", formData.materialId],
    queryFn: () => apiFetch<{ tags: string[] }>(`/tags${buildQuery({ material_id: formData.materialId || undefined })}`),
  });

  const updateFormData = useCallback((updates: Partial<AddNoteRequest>) => {
    setFormData(prev => ({ ...prev, ...updates }));
    setError(null);
  }, []);

  const addMut = useMutation({
    mutationFn: async () => {
      if (!isUuid(formData.materialId)) {
        throw new Error("Choose a valid material (UUID)");
      }
      const body: Record<string, unknown> = {
        material_id: formData.materialId,
        content: formData.content,
        chapter: formData.chapter || "",
        page: formData.page,
        tags: formData.tags,
      };
      if (formData.title.trim()) {
        body.title = formData.title.trim();
      }
      if (formData.linkId.trim() && isUuid(formData.linkId.trim())) {
        body.link_id = formData.linkId.trim();
      }
      return apiFetch<{ note_id: string }>("/add", {
        method: "POST",
        body: JSON.stringify(body),
      });
    },
    onMutate: async () => {
      await new Promise(resolve => setTimeout(resolve, 0));
      setSuccessId("optimistic");
    },
    onSuccess: (data) => {
      setSuccessId(data?.note_id ?? null);
      setFormData({
        materialId: "",
        title: "",
        content: "",
        tags: [],
        linkId: "",
        chapter: "",
        page: 0,
      });
    },
    onError: (e: Error) => {
      setSuccessId(null);
      setError(e.message);
    },
  });

  const titles = titlesQ.data?.items ?? {};
  const hasTitles = Object.keys(titles).length > 0;
  const availableTags = tagListQ.data?.tags ?? [];

  const materialOptions = useMemo(() => {
    return Object.keys(titles).sort((a, b) =>
        (titles[a] ?? "").localeCompare(titles[b] ?? ""),
    );
  }, [titlesQ]);

  // TODO
  const pageLabel = "page number";
  const chapterLabel = "chapter";

  if (titlesQ.error || tagListQ.error) {
    return <p className="error">{((titlesQ.error || tagListQ.error) as Error).message}</p>;
  }

  if (!titlesQ.isLoading && !hasTitles) {
    return <div className="not-found"><p className="message">No materials found</p></div>;
  }

  return (
      <>
        {successId ? (
            <div className="alert success hover add-note-alert" id={successId}>
              {successId === "optimistic" ? "Pending..." : `Note '${successId}' created`}
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
            <fieldset className="fieldset">
              <legend className="legend">Add note</legend>

              <ComboboxRoot
                  options={materialOptions}
                  getOptionLabel={(id) => titles[id] || id}
                  value={formData.materialId}
                  onChange={(id) => updateFormData({ materialId: id })}
              >
                <ComboboxInput
                    placeholder="Choose a material"
                    className="input input-datalist"
                    title="ID of the material"
                />
                <ComboboxList />
              </ComboboxRoot>

              <input
                  className="input"
                  placeholder="Enter a title"
                  value={formData.title}
                  title="Title of the note"
                  onChange={(e) => updateFormData({ title: e.target.value })}
              />

              <textarea
                  ref={contentRef}
                  className="input altch"
                  placeholder="Enter a content"
                  value={formData.content}
                  title="Text of the note"
                  onChange={(e) => updateFormData({ content: e.target.value })}
                  rows={6}
              />

              <SpellErrorsList spellErrors={spellErrors} onReplace={replaceWord} />

              <ComboboxRoot
                  multiple
                  options={availableTags}
                  getOptionLabel={(tag) => `#${tag}`}
                  value={formData.tags}
                  onChange={(tags) => updateFormData({ tags })}
                  allowCreate
              >
                <ComboboxInput
                    className="input"
                    placeholder="Enter tags"
                    title="Tags for the note"
                />
                <ComboboxList />
              </ComboboxRoot>

              <input
                  className="input"
                  placeholder="Enter a link"
                  value={formData.linkId}
                  title="Link to the other note"
                  onChange={(e) => updateFormData({ linkId: e.target.value })}
              />

              <input
                  className="input"
                  placeholder={`Enter a ${chapterLabel}`}
                  value={formData.chapter}
                  title={`${chapterLabel} where the note might be found`}
                  onChange={(e) => updateFormData({ chapter: e.target.value })}
              />

              <input
                  className="input"
                  type="number"
                  placeholder={`Enter a ${pageLabel}`}
                  value={formData.page || ""}
                  title={`${pageLabel} where the note might be found`}
                  onChange={(e) => updateFormData({ page: Number(e.target.value) || 0 })}
                  min={0}
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

        {error && <p className="error">{error}</p>}
      </>
  );
}