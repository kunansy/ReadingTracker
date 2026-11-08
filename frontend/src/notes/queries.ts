import { useQuery } from "@tanstack/react-query";

import { api, unwrap } from "../api/client";

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
