import { createApiFetch } from "./client";

const API_BASE =
  import.meta.env.VITE_READING_LOG_API_BASE ?? "/api/v1/cards";

export const apiFetch = createApiFetch(API_BASE);
export { buildQuery } from "./client";
