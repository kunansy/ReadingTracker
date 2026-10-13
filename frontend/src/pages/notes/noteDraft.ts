export type NoteDraft = {
  materialId: string;
  chapter: string;
  page: number;
};

export function parseNoteDraft(value: unknown): NoteDraft | null {
  if (
    typeof value !== "object" ||
    value === null ||
    !("materialId" in value) ||
    !("chapter" in value) ||
    !("page" in value)
  ) {
    return null;
  }
  const { materialId, chapter, page } = value;
  if (
    typeof materialId !== "string" ||
    typeof chapter !== "string" ||
    typeof page !== "number" ||
    !Number.isFinite(page)
  ) {
    return null;
  }
  return { materialId, chapter, page };
}

export function resolveNoteDraft(initialMaterial: string, draft: NoteDraft | null): NoteDraft {
  const materialId = initialMaterial || draft?.materialId || "";
  if (draft === null || draft.materialId !== materialId) {
    return { materialId, chapter: "", page: 0 };
  }
  return { materialId, chapter: draft.chapter, page: draft.page };
}
