import { RefObject, useEffect } from "react";

type HotkeyOptions = {
  disabled?: boolean;
  readOnly?: boolean;
};

type WrapSpec = {
  prefix: string;
  suffix: string;
};

const UUID_RE =
    /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/;

const STOP_CHARS = new Set([" ", "\n", "\r", "\t"]);

function isTextField(
    el: EventTarget | null,
): el is HTMLTextAreaElement | HTMLInputElement {
  return el instanceof HTMLTextAreaElement || el instanceof HTMLInputElement;
}

function findWordBounds(value: string, caret: number) {
  let start = caret;
  let end = caret;

  while (start > 0 && !STOP_CHARS.has(value[start - 1])) {
    start--;
  }

  while (end < value.length && !STOP_CHARS.has(value[end])) {
    end++;
  }

  return { start, end };
}

function buildWrappedValue(
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

function buildInsertedValue(
    value: string,
    caret: number,
    insert: string,
) {
  const nextValue = `${value.slice(0, caret)}${insert}${value.slice(caret)}`;
  const nextCaret = caret + insert.length;
  return { nextValue, nextCaret };
}

export function useAltchHotkeys(
    ref: RefObject<HTMLTextAreaElement | HTMLInputElement | null>,
    value: string,
    onChange: (value: string) => void,
    options: HotkeyOptions = {},
) {
  useEffect(() => {
    const field = ref.current;
    if (!field || options.disabled || options.readOnly) return;

    const applyValue = (
        nextValue: string,
        selectionStart: number,
        selectionEnd: number,
    ) => {
      onChange(nextValue);
      requestAnimationFrame(() => {
        field.focus();
        field.setSelectionRange(selectionStart, selectionEnd);
      });
    };

    const onKeyDown = async (e: KeyboardEvent) => {
      if (e.defaultPrevented || !isTextField(e.target)) return;
      if (e.metaKey && e.ctrlKey) return;

      const input = e.target;
      const rawStart = input.selectionStart ?? 0;
      const rawEnd = input.selectionEnd ?? 0;
      const collapsed = rawStart === rawEnd;

      const { start, end } = collapsed
          ? findWordBounds(input.value, rawStart)
          : { start: rawStart, end: rawEnd };

      const wrap = (spec: WrapSpec) => {
        const { nextValue, nextStart, nextEnd } = buildWrappedValue(
            value,
            start,
            end,
            spec.prefix,
            spec.suffix,
        );
        applyValue(nextValue, nextStart, nextEnd);
      };

      if (e.ctrlKey && e.key.toLowerCase() === "q") {
        wrap({ prefix: "«", suffix: "»" });
        e.preventDefault();
        return;
      }

      if (e.ctrlKey && e.key.toLowerCase() === "b") {
        wrap({ prefix: "**", suffix: "**" });
        e.preventDefault();
        return;
      }

      if (e.ctrlKey && e.key.toLowerCase() === "i") {
        wrap({ prefix: "*", suffix: "*" });
        e.preventDefault();
        return;
      }

      if (e.ctrlKey && e.key.toLowerCase() === "j") {
        wrap({ prefix: "`", suffix: "`" });
        e.preventDefault();
        return;
      }

      if (e.altKey && e.key === "ArrowDown") {
        wrap({ prefix: "<sub>", suffix: "</sub>" });
        e.preventDefault();
        return;
      }

      if (e.altKey && e.key === "ArrowUp") {
        wrap({ prefix: "<sup>", suffix: "</sup>" });
        e.preventDefault();
        return;
      }

      if (e.ctrlKey && e.key.toLowerCase() === "t") {
        const caret = rawEnd;
        const { nextValue, nextCaret } = buildInsertedValue(value, caret, "–");
        applyValue(nextValue, nextCaret, nextCaret);
        e.preventDefault();
        return;
      }

      if (e.ctrlKey && e.key.toLowerCase() === "k") {
        const text = (await navigator.clipboard.readText()).trim();
        if (UUID_RE.test(text)) {
          const caret = rawEnd;
          const insert = `\n[[${text}]]`;
          const { nextValue, nextCaret } = buildInsertedValue(
              value,
              caret,
              insert,
          );
          applyValue(nextValue, nextCaret, nextCaret);
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