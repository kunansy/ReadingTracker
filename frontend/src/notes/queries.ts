import { skipToken, useQuery } from "@tanstack/react-query";

import { api, unwrap } from "../api/client";
import { isUuid } from "../utils/isUuid.ts";

const META_STALE_TIME_MS = 10 * 60 * 1000;

export const noteKeys = {
  all: ["notes"],
  byId: (noteId: string) => ["notes", noteId] as const,
  meta: (materialId: string) => ["notes", "meta", materialId] as const,
  search: (query: object) => ["notes", "search", query] as const,
  links: (noteId: string, nextToken: string | undefined, order: string) =>
    ["notes", "links", noteId, nextToken, order] as const,
  possibleLinks: (noteId: string) => ["notes", "possible-links", noteId] as const,
  tags: (materialId: string) => ["notes", "tags", materialId] as const,
  graph: (materialId: string) => ["notes", "graph", materialId] as const,
  autocomplete: (query: string) => ["notes", "autocomplete", query] as const,
} as const;

export function isLinksKeyOf(queryKey: readonly unknown[], noteId: string): boolean {
  return queryKey[0] === "notes" && queryKey[1] === "links" && queryKey[2] === noteId;
}

/** An empty `materialId` loads the meta of all materials. */
export function useNotesMeta(materialId = "") {
  return useQuery({
    queryKey: noteKeys.meta(materialId),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/notes/meta", {
          params: { query: { material_id: materialId || undefined } },
        }),
      ),
    staleTime: META_STALE_TIME_MS,
  });
}

export function useNote(noteId: string) {
  return useQuery({
    queryKey: noteKeys.byId(noteId),
    queryFn: noteId
      ? () => unwrap(api.GET("/api/v1/notes/{note_id}", { params: { path: { note_id: noteId } } }))
      : skipToken,
  });
}

/** An empty `materialId` loads the tags of all materials unless `requireMaterial` is set. */
export function useNoteTags(materialId: string, { requireMaterial = false } = {}) {
  const isSkipped = requireMaterial && !isUuid(materialId);
  return useQuery({
    queryKey: noteKeys.tags(materialId),
    queryFn: isSkipped
      ? skipToken
      : () =>
          unwrap(
            api.GET("/api/v1/notes/tags", {
              params: { query: { material_id: materialId || undefined } },
            }),
          ),
  });
}
