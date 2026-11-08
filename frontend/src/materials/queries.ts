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
