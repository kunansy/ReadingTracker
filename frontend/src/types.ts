import { materialTypesEnumValues, type MaterialTypesEnum } from "./api/schema";

export type MaterialType = MaterialTypesEnum;

export const MaterialTypes: readonly MaterialType[] = materialTypesEnumValues;

export function isMaterialType(value: string): value is MaterialType {
  return MaterialTypes.some((materialType) => materialType === value);
}

export type SpellError = {
  word: string;
  suggestions: string[];
};

export type AddNoteRequest = {
  materialId: string;
  title: string;
  content: string;
  tags: string[];
  linkId: string;
  chapter: string;
  page: number;
};
