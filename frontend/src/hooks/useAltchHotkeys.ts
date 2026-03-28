import { type RefObject, useEffect } from "react";

const UUID_RE =
  /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/;

function surroundSelection(
  field: HTMLInputElement | HTMLTextAreaElement,
  prefix: string,
  suffix: string,
) {
  const before = field.value.substring(0, field.selectionStart ?? 0);
  const sel = field.value.substring(
    field.selectionStart ?? 0,
    field.selectionEnd ?? 0,
  );
  const after = field.value.substring(field.selectionEnd ?? 0);
  field.value = `${before}${prefix}${sel}${suffix}${after}`;
}

export function useAltchHotkeys(
  ref: RefObject<HTMLInputElement | HTMLTextAreaElement | null>,
) {
  useEffect(() => {
    const field = ref.current;
    if (!field) {
      return;
    }
    const onKeyDown = async (e: KeyboardEvent) => {
      const input = e.target as HTMLInputElement;
      if (e.keyCode === 81 && e.ctrlKey) {
        surroundSelection(input, "«", "»");
        e.preventDefault();
      } else if (e.keyCode === 84 && e.ctrlKey) {
        input.value += "–";
        e.preventDefault();
      } else if (e.keyCode === 66 && e.ctrlKey) {
        surroundSelection(input, "**", "**");
        e.preventDefault();
      } else if (e.keyCode === 73 && e.ctrlKey) {
        surroundSelection(input, "*", "*");
        e.preventDefault();
      } else if (e.keyCode === 74 && e.ctrlKey) {
        surroundSelection(input, "`", "`");
        e.preventDefault();
      } else if (e.keyCode === 40 && e.altKey) {
        surroundSelection(input, "<sub>", "</sub>");
        e.preventDefault();
      } else if (e.keyCode === 38 && e.altKey) {
        surroundSelection(input, "<sup>", "</sup>");
        e.preventDefault();
      } else if (e.keyCode === 75 && e.ctrlKey) {
        let text = await navigator.clipboard.readText();
        text = text.trim();
        if (UUID_RE.test(text)) {
          input.value += `\n[[${text}]]`;
        }
        e.preventDefault();
      }
    };
    field.addEventListener("keydown", onKeyDown, true);
    return () => {
      field.removeEventListener("keydown", onKeyDown, true);
    };
  }, [ref]);
}
