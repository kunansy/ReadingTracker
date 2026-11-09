export const systemKeys = {
  all: ["system-graphics"],
  summary: (lastDays: number) => ["system-graphics", "summary", lastDays] as const,
  graphic: (name: string, params: object = {}) => ["system-graphics", name, params] as const,
} as const;
