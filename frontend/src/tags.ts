import { TAG_MAX_LENGTH, TAG_PATTERN } from "./api/constraints";

export type SanitizedInput = { value: string; notice: string | null };

const tagRe = new RegExp(TAG_PATTERN, "u");
const SEPARATOR = "_";

export const TAG_SEPARATOR_NOTICE = "Spaces and symbols become _";
export const TAG_LENGTH_NOTICE = `Tags are limited to ${TAG_MAX_LENGTH} characters`;

function replaceSeparators(chars: readonly string[]): string[] {
  return chars.reduce<string[]>((out, ch) => {
    if (tagRe.test(ch)) {
      return [...out, ch];
    }
    const previous = out[out.length - 1];
    return out.length === 0 || previous === SEPARATOR ? out : [...out, SEPARATOR];
  }, []);
}

export function sanitizeTagInput(raw: string): SanitizedInput {
  const lowered = Array.from(raw.toLowerCase());
  const replaced = replaceSeparators(lowered);
  const value = replaced.slice(0, TAG_MAX_LENGTH).join("");

  if (replaced.length > TAG_MAX_LENGTH) {
    return { value, notice: TAG_LENGTH_NOTICE };
  }
  return { value, notice: replaced.join("") === lowered.join("") ? null : TAG_SEPARATOR_NOTICE };
}

export function toTag(input: string): string {
  return input.trim().replace(/^_+|_+$/g, "");
}
