export const cardKeys = {
  all: ["cards"],
  list: (query: object) => ["cards", "list", query] as const,
  notesWithCards: (materialId: string) => ["cards", "notes-with-cards", materialId] as const,
} as const;
