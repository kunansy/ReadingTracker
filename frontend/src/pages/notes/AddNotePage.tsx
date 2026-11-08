import { useMutation, useQuery } from "@tanstack/react-query";
import {useState, useCallback, useMemo, useEffect} from "react";
import { useSearchParams } from "react-router-dom";

import { api, errorMessage, unwrap } from "../../api/client";
import type { AddNoteRequest } from "../../api/schema";
import { CelebrateButton } from "../../components/CelebrateButton";
import { ComboboxInput, ComboboxList, ComboboxRoot } from "../../components/Combobox.tsx";
import {isUuid} from "../../utils/isUuid.ts";
import {SpellTextarea} from "../../components/SpellTextrea.tsx";
import { loadWithTtl, saveWithTtl } from "../../lib/ttlStorage.ts";
import { NoteDraft, parseNoteDraft, resolveNoteDraft } from "./noteDraft.ts";
import { useMaterial, useMaterialTitles } from "../../materials/queries";
import { noteKeys } from "../../notes/queries";

type AddNoteForm = NoteDraft & {
  title: string;
  content: string;
  tags: string[];
  linkId: string;
};

const NOTE_DRAFT_KEY = "add-note-draft";
const NOTE_DRAFT_TTL_MS = 12 * 60 * 60 * 1000;


export function AddNotePage() {
  const [searchParams] = useSearchParams();
  const initialMaterial = searchParams.get("material_id") ?? "";
  const [pageName, setPageName] = useState("page number");
  const [chapterName, setChapterName] = useState("chapter");

  const [formData, setFormData] = useState<AddNoteForm>(() => ({
    ...resolveNoteDraft(initialMaterial, parseNoteDraft(loadWithTtl(NOTE_DRAFT_KEY))),
    title: "",
    content: "",
    tags: [],
    linkId: "",
  }));
  const [successId, setSuccessId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const titlesQ = useMaterialTitles();

  const tagListQ = useQuery({
    queryKey: noteKeys.tags(formData.materialId),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/notes/tags", {
          params: { query: { material_id: formData.materialId || undefined } },
        }),
      ),
  });
  const materialId = initialMaterial || formData.materialId;
  const materialQ = useMaterial(materialId);

  useEffect(() => {
    const materialType = materialQ.data?.material.material_type || "book";
    setPageName("Page");
    setChapterName("Chapter");
    if (materialType === "lecture" || materialType === "audiobook") {
      setPageName("Minute");
    }
    if (materialType === "course") {
      setPageName("Lecture");
      setChapterName("Block");
    }
  }, [materialQ.data?.material.material_type]);

  const updateFormData = useCallback((updates: Partial<AddNoteForm>) => {
    setFormData(prev => ({ ...prev, ...updates }));
    setError(null);
  }, []);

  const addMut = useMutation({
    mutationFn: async (request: AddNoteForm) => {
      if (!isUuid(request.materialId)) {
        throw new Error("Choose a valid material (UUID)");
      }
      const linkId = request.linkId.trim();
      const body: AddNoteRequest = {
        material_id: request.materialId,
        content: request.content,
        chapter: request.chapter || "",
        page: request.page,
        tags: request.tags,
        title: request.title.trim() || undefined,
        link_id: isUuid(linkId) ? linkId : undefined,
      };
      return unwrap(api.POST("/api/v1/notes/add", { body }));
    },
    onMutate: async () => {
      await new Promise(resolve => setTimeout(resolve, 0));
      setSuccessId("optimistic");
    },
    onSuccess: (data, request) => {
      setSuccessId(data.note_id);
      const { materialId, chapter, page } = request;
      saveWithTtl<NoteDraft>(NOTE_DRAFT_KEY, { materialId, chapter, page }, NOTE_DRAFT_TTL_MS);
      // Fields edited while the request was in flight were not submitted, so they are kept.
      setFormData(prev => ({
        ...prev,
        title: prev.title === request.title ? "" : prev.title,
        content: prev.content === request.content ? "" : prev.content,
        tags: prev.tags === request.tags ? [] : prev.tags,
        linkId: prev.linkId === request.linkId ? "" : prev.linkId,
      }));
    },
    onError: (e: unknown) => {
      setSuccessId(null);
      setError(errorMessage(e));
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

  const loadError = titlesQ.error || tagListQ.error;
  if (loadError) {
    return <p className="error">{loadError.message}</p>;
  }

  if (!titlesQ.isLoading && !hasTitles) {
    return <div className="not-found"><p className="message">No materials found</p></div>;
  }

  return (
      <>
        {materialQ.error ? (
            <p className="error" role="alert">Failed to load material: {materialQ.error.message}</p>
        ) : null}
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
            addMut.mutate(formData);
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
                    className="input"
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

              <SpellTextarea
                  className="input"
                  placeholder="Enter a content"
                  value={formData.content}
                  onChange={(content) => updateFormData({ content })}
                  style={{ height: "30vh", }}
              />

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
                  placeholder={`Enter a ${chapterName.toLowerCase()}`}
                  value={formData.chapter}
                  title={`${chapterName} where the note might be found`}
                  onChange={(e) => updateFormData({ chapter: e.target.value })}
              />

              <input
                  className="input"
                  type="number"
                  placeholder={`Enter a ${pageName.toLowerCase()}`}
                  value={formData.page || ""}
                  title={`${pageName} where the note might be found`}
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