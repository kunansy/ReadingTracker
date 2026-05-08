import { RefObject, useEffect } from "react";

type HotkeyAction = {
  prefix: string;
  suffix: string;
};

type Options = {
  disabled?: boolean;
  readOnly?: boolean;
};

function applyWrap(
  value: string,
  start: number,
  end: number,
  prefix: string,
  suffix: string,
) {
  const before = value.slice(0, start);
  const selected = value.slice(start, end);
  const after = value.slice(end);

  const nextValue = `${before}${prefix}${selected}${suffix}${after}`;
  const nextStart = start + prefix.length;
  const nextEnd = end + prefix.length;

  return { nextValue, nextStart, nextEnd };
}

function applyAppend(value: string, insert: string, caretPos: number) {
  const nextValue = value.slice(0, caretPos) + insert + value.slice(caretPos);
  const nextCaret = caretPos + insert.length;
  return { nextValue, nextCaret };
}

export function useAltchHotkeys(
  ref: RefObject<HTMLTextAreaElement | HTMLInputElement | null>,
  value: string,
  onChange: (value: string) => void,
  options: Options = {},
) {
  useEffect(() => {
    const field = ref.current;
    if (!field || options.disabled || options.readOnly) return;

    const restoreSelection = (start: number, end: number) => {
      requestAnimationFrame(() => {
        field.focus();
        field.setSelectionRange(start, end);
      });
    };

    const commit = (nextValue: string, start?: number, end?: number) => {
      onChange(nextValue);
      if (start !== undefined && end !== undefined) {
        restoreSelection(start, end);
      }
    };

    const onKeyDown = async (e: KeyboardEvent) => {
      if (e.defaultPrevented) return;
      if (!(e.target instanceof HTMLTextAreaElement || e.target instanceof HTMLInputElement)) {
        return;
      }

      const input = e.target;
      const start = input.selectionStart ?? 0;
      const end = input.selectionEnd ?? 0;
      const hasSelection = start !== end;

      if (e.ctrlKey && e.key.toLowerCase() === "q") {
        const { nextValue, nextStart, nextEnd } = applyWrap(value, start, end, "«", "»");
        commit(nextValue, nextStart, nextEnd);
        e.preventDefault();
        return;
      }

      if (e.ctrlKey && e.key.toLowerCase() === "t") {
        const { nextValue, nextCaret } = applyAppend(value, "–", end);
        commit(nextValue, nextCaret, nextCaret);
        e.preventDefault();
        return;
      }

      if (e.ctrlKey && e.key.toLowerCase() === "b") {
        const { nextValue, nextStart, nextEnd } = applyWrap(value, start, end, "**", "**");
        commit(nextValue, nextStart, nextEnd);
        e.preventDefault();
        return;
      }

      if (e.ctrlKey && e.key.toLowerCase() === "i") {
        const { nextValue, nextStart, nextEnd } = applyWrap(value, start, end, "*", "*");
        commit(nextValue, nextStart, nextEnd);
        e.preventDefault();
        return;
      }

      if (e.ctrlKey && e.key.toLowerCase() === "j") {
        const { nextValue, nextStart, nextEnd } = applyWrap(value, start, end, "`", "`");
        commit(nextValue, nextStart, nextEnd);
        e.preventDefault();
        return;
      }

      if (e.altKey && e.key === "ArrowDown") {
        const { nextValue, nextStart, nextEnd } = applyWrap(value, start, end, "<sub>", "</sub>");
        commit(nextValue, nextStart, nextEnd);
        e.preventDefault();
        return;
      }

      if (e.altKey && e.key === "ArrowUp") {
        const { nextValue, nextStart, nextEnd } = applyWrap(value, start, end, "<sup>", "</sup>");
        commit(nextValue, nextStart, nextEnd);
        e.preventDefault();
        return;
      }

      if (e.ctrlKey && e.key.toLowerCase() === "k") {
        const text = (await navigator.clipboard.readText()).trim();
        if (/^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/.test(text)) {
          const insert = `\n[[${text}]]`;
          const { nextValue, nextCaret } = applyAppend(value, insert, end);
          commit(nextValue, nextCaret, nextCaret);
          e.preventDefault();
        }
      }
    };

    field.addEventListener("keydown", onKeyDown, true);
    return () => {
      field.removeEventListener("keydown", onKeyDown, true);
    };
  }, [ref, value, onChange, options.disabled, options.readOnly]);
}