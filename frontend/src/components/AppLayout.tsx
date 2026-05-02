import { ReactNode, useEffect, useId, useState } from "react";
import { NavLink } from "react-router-dom";

type PrimaryLink = { label: string; to: string };

const PRIMARY_LINKS: PrimaryLink[] = [
  { label: "Materials", to: "/materials" },
  { label: "Reading log", to: "/reading_logs" },
  { label: "Notes", to: "/notes" },
  { label: "Cards", to: "/cards" },
  { label: "System", to: "/system" },
];

export function AppLayout({
  subnav,
  children,
}: {
  subnav?: ReactNode;
  children: ReactNode;
}) {
  const navId = useId();
  const [isNavOpen, setIsNavOpen] = useState(false);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setIsNavOpen(false);
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  return (
    <div className="page">
      <header className="appHeader">
        <div className="appTopbar">
          <div className="appBrand">Reading tracker</div>

          <button
            type="button"
            className="navToggle"
            aria-label={isNavOpen ? "Close navigation" : "Open navigation"}
            aria-expanded={isNavOpen}
            aria-controls={navId}
            onClick={() => setIsNavOpen((v) => !v)}
          >
            <span className="navToggle__icon" aria-hidden="true" />
          </button>

          <nav
            id={navId}
            className={`navbar ${isNavOpen ? "navbar--open" : ""}`.trim()}
            aria-label="Primary navigation"
            onClick={(e) => {
              const target = e.target as HTMLElement | null;
              if (target?.closest("a")) setIsNavOpen(false);
            }}
          >
            {PRIMARY_LINKS.map(({ label, to }) => (
              <NavLink key={to} to={to} className="navbar__link">
                {label}
              </NavLink>
            ))}
          </nav>
        </div>

        {subnav ? <div className="appSubnav">{subnav}</div> : null}
      </header>

      <div className="appBody">
        {subnav ? <aside className="appSidebar">{subnav}</aside> : null}
        <main className="appMain">
          <div id="loader" />
          {children}
        </main>
      </div>

      <footer id="footer" />
    </div>
  );
}
