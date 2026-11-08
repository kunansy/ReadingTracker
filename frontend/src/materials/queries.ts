import { useQuery } from "@tanstack/react-query";

import { api, unwrap } from "../api/client";

const LOOKUP_STALE_TIME_MS = 5 * 60 * 1000;

export const materialKeys = {
  all: ["materials"],
  tags: ["materials", "tags"],
  authors: ["materials", "authors"],
  titles: ["materials", "titles"],
  readTitles: ["materials", "read_titles"],
  readingNow: ["materials", "reading_now"],
  readingTitles: ["materials", "reading_titles"],
  withCardsTitles: ["materials", "with_cards_titles"],
  queue: ["materials", "queue"],
  reading: ["materials", "reading"],
  byId: (materialId: string) => ["materials", materialId] as const,
  completionInfo: (materialId: string) => ["materials", materialId, "completion-info"] as const,
  repeat: (query: object) => ["materials", "repeat", query] as const,
  completedItem: (materialId: string) => ["materials", "completed", "item", materialId] as const,
  completedList: (filtersKey: string, nextToken: string | undefined, order: string) =>
    ["materials", "completed", "list", filtersKey, nextToken, order] as const,
} as const;

export function useMaterialTags() {
  return useQuery({
    queryKey: materialKeys.tags,
    queryFn: () => unwrap(api.GET("/api/v1/materials/tags")),
    staleTime: LOOKUP_STALE_TIME_MS,
  });
}

export function useMaterialAuthors() {
  return useQuery({
    queryKey: materialKeys.authors,
    queryFn: () => unwrap(api.GET("/api/v1/materials/authors")),
    staleTime: LOOKUP_STALE_TIME_MS,
  });
}

export function useMaterialTitles() {
  return useQuery({
    queryKey: materialKeys.titles,
    queryFn: () => unwrap(api.GET("/api/v1/materials/titles")),
  });
}

export function useReadMaterialTitles() {
  return useQuery({
    queryKey: materialKeys.readTitles,
    queryFn: () => unwrap(api.GET("/api/v1/materials/read-titles")),
    staleTime: LOOKUP_STALE_TIME_MS,
  });
}

export function useMaterialReadingNow() {
  return useQuery({
    queryKey: materialKeys.readingNow,
    queryFn: () => unwrap(api.GET("/api/v1/reading_logs/material-reading-now")),
  });
}

export function useReadingMaterialTitles() {
  return useQuery({
    queryKey: materialKeys.readingTitles,
    queryFn: () => unwrap(api.GET("/api/v1/materials/reading-titles")),
    staleTime: LOOKUP_STALE_TIME_MS,
  });
}

export function useMaterialsWithCardsTitles() {
  return useQuery({
    queryKey: materialKeys.withCardsTitles,
    queryFn: () => unwrap(api.GET("/api/v1/materials/with-cards-titles")),
    staleTime: LOOKUP_STALE_TIME_MS,
  });
}

export function useMaterial(materialId: string | null | undefined) {
  return useQuery({
    queryKey: materialKeys.byId(materialId ?? ""),
    enabled: Boolean(materialId),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/materials/{material_id}", {
          params: { path: { material_id: materialId ?? "" } },
        }),
      ),
  });
}
