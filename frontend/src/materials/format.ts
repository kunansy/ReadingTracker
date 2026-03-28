export function itemsLabel(materialType: string): string {
  if (materialType === "lecture") {
    return "Minutes";
  }
  if (materialType === "course") {
    return "Lectures";
  }
  return "Pages";
}

export function itemsLabelLower(materialType: string): string {
  return itemsLabel(materialType).toLowerCase();
}
