import type { MaterialTypesEnum } from "../api/schema";

export function itemsLabel(materialType: MaterialTypesEnum): string {
  if (materialType === "lecture") {
    return "Minutes";
  }
  if (materialType === "course") {
    return "Lectures";
  }
  return "Pages";
}

export function itemsLabelLower(materialType: MaterialTypesEnum): string {
  return itemsLabel(materialType).toLowerCase();
}
