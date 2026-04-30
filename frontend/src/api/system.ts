import { createApiFetch } from "./client";

const API_BASE = import.meta.env.VITE_SYSTEM_API_BASE ?? "/api/v1/system";

export const apiFetch = createApiFetch(API_BASE);
export { buildQuery } from "./client";

