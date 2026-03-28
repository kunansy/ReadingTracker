import { useRef, type ButtonHTMLAttributes, type ReactNode } from "react";

import { celebrateAtEvent } from "../lib/celebrate";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  children: ReactNode;
};

export function CelebrateButton({
  children,
  className = "",
  type = "button",
  onMouseEnter,
  onMouseLeave,
  ...rest
}: Props) {
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  return (
    <button
      type={type}
      {...rest}
      className={`celebrate-btn ${className}`.trim()}
      onMouseEnter={(e) => {
        timeoutRef.current = setTimeout(() => {
          celebrateAtEvent(e);
        }, 150);
        onMouseEnter?.(e);
      }}
      onMouseLeave={(e) => {
        if (timeoutRef.current) {
          clearTimeout(timeoutRef.current);
          timeoutRef.current = null;
        }
        onMouseLeave?.(e);
      }}
    >
      {children}
    </button>
  );
}
