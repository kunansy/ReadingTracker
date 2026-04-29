import { NavLink } from "react-router-dom";

const links: { name: string; to: string; className: string }[] = [
  { name: "Cards", to: ".", className: "list-nav" },
  { name: "Add card", to: "add", className: "add-nav" },
];

export function CardsSubnav() {
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
