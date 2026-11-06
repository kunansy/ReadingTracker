export type SortOrder = "asc" | "desc";

export function reverseOrder(order: SortOrder): SortOrder {
  return order === "asc" ? "desc" : "asc";
}
