import { materialTypesEnumValues, type MaterialTypesEnum } from "./api/schema";

export function isMaterialType(value: string): value is MaterialTypesEnum {
  return materialTypesEnumValues.some((materialType) => materialType === value);
}

export type SpellError = {
  word: string;
  suggestions: string[];
};
