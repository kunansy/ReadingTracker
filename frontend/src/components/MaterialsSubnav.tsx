import { NavLink } from "react-router-dom";

const links: { name: string; to: string; className: string }[] = [
  { name: "Queue", to: "queue", className: "queue-nav" },
  { name: "Reading", to: "reading", className: "reading-nav" },
  { name: "Completed", to: "completed", className: "completed-nav" },
  { name: "Repeat", to: "repeat-view", className: "repeat-nav" },
  { name: "Add material", to: "add-view", className: "add material-nav" },
];

export function MaterialsSubnav() {
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
