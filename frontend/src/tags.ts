import { TAG_MAX_LENGTH, TAG_PATTERN } from "./api/constraints";

const tagRe = new RegExp(TAG_PATTERN, "u");

export function sanitizeTagInput(raw: string): string {
  return Array.from(raw.toLowerCase())
    .filter((ch) => tagRe.test(ch))
    .slice(0, TAG_MAX_LENGTH)
    .join("");
}
