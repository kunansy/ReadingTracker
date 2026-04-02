import { createApiFetch } from "./client";

const API_BASE = import.meta.env.VITE_API_BASE ?? "/api/v1/notes";

export const apiFetch = createApiFetch(API_BASE);
export { buildQuery } from "./client";
