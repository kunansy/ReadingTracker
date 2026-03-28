import { createApiFetch } from "./client";

const API_BASE =
  import.meta.env.VITE_MATERIALS_API_BASE ?? "/api/v1/materials";

export const apiFetch = createApiFetch(API_BASE);
export { buildQuery } from "./client";
