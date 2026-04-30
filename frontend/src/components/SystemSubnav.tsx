import { NavLink } from "react-router-dom";

const links: { name: string; to: string; className: string }[] = [
    { name: "Graphics", to: ".", className: "system-nav" },
    { name: "Backup", to: "backup", className: "backup-nav" },
    { name: "Restore", to: "restore", className: "restore-nav" },
];

export function SystemSubnav() {
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
