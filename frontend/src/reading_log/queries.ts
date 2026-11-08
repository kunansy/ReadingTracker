export const readingLogKeys = {
  all: ["reading_logs"],
  list: (query: object) => ["reading_logs", "list", query] as const,
} as const;
