import React, { useRef } from "react";
import { useAltchHotkeys } from "../hooks/useAltchHotkeys";
import { useSpellChecker } from "../hooks/useSpellChecker";
import { SpellErrorsList } from "./SpellErrorsList";

type SpellTextareaProps = {
  value: string;
  onChange: (value: string) => void;
  className?: string;
  placeholder?: string;
  style?: React.CSSProperties;
  disabled?: boolean;
  readOnly?: boolean;
  name?: string;
  id?: string;
};

export function SpellTextarea({
  value,
  onChange,
  className,
  placeholder,
  style,
  disabled,
  readOnly,
  name,
  id,
}: SpellTextareaProps) {
  const contentRef = useRef<HTMLTextAreaElement>(null);

  // TODO: fix the hook
  useAltchHotkeys(contentRef, value, onChange, { disabled, readOnly });

  const { spellErrors, replaceWord } = useSpellChecker(value, onChange);

  return (
    <div className="spell-textarea">
      <textarea
        ref={contentRef}
        className={className}
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        style={style}
        disabled={disabled}
        readOnly={readOnly}
        name={name}
        id={id}
      />

      <SpellErrorsList spellErrors={spellErrors} onReplace={replaceWord} />
    </div>
  );
}
