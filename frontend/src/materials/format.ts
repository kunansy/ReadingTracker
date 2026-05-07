import {MaterialType} from "../types.ts";

export function itemsLabel(materialType: string): string {
  if (materialType === MaterialType.lecture) {
    return "Minutes";
  }
  if (materialType === MaterialType.course) {
    return "Lectures";
  }
  return "Pages";
}

export function itemsLabelLower(materialType: string): string {
  return itemsLabel(materialType).toLowerCase();
}
