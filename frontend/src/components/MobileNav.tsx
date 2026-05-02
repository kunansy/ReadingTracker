import { useEffect, useId, useState } from "react";

type LinkItem = { label: string; href: string };

const LINKS: LinkItem[] = [
  { label: "Materials", href: "/materials" },
  { label: "Reading log", href: "/reading_logs" },
  { label: "Notes", href: "/notes" },
  { label: "Cards", href: "/cards" },
  { label: "System", href: "/system" },
];

export function MobileNav() {
  const menuId = useId();
  const [open, setOpen] = useState(false);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  return (
    <div className="mobileNav">
      <div className="mobileNav__bar">
        <div className="mobileNav__brand">Reading tracker</div>
        <button
          type="button"
          className="mobileNav__toggle"
          aria-label={open ? "Close menu" : "Open menu"}
          aria-expanded={open}
          aria-controls={menuId}
          onClick={() => setOpen((v) => !v)}
        >
          <span className="mobileNav__icon" aria-hidden="true" />
        </button>
      </div>

      <div
        id={menuId}
        className={`mobileNav__menu ${open ? "mobileNav__menu--open" : ""}`.trim()}
        role="dialog"
        aria-label="Navigation menu"
        aria-modal="true"
        onClick={(e) => {
          const target = e.target as HTMLElement | null;
          if (target?.closest("a")) setOpen(false);
        }}
      >
        {LINKS.map((l) => (
          <a key={l.href} href={l.href} className="mobileNav__link">
            {l.label}
          </a>
        ))}
      </div>
    </div>
  );
}
