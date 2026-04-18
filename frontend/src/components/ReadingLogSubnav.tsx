import { NavLink } from "react-router-dom";

const links: { name: string; to: string; className: string }[] = [
  { name: "Reading log", to: "list", className: "list-nav" },
  { name: "Add log record", to: "add", className: "add-nav" },
];

export function ReadingLogSubnav() {
  return (
    <nav className="subnavbar">
      {links.map(({ name, to, className }) => (
        <NavLink
          key={to}
          to={to}
          className={({ isActive }) =>
            `${className}${isActive ? " active" : ""}`.trim()
          }
        >
          {name}
        </NavLink>
      ))}
    </nav>
  );
}
