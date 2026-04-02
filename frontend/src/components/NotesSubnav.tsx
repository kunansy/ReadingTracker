import { NavLink, useSearchParams } from "react-router-dom";

export function NotesSubnav() {
  const [searchParams] = useSearchParams();
  const materialId = searchParams.get("material_id");
  const graphTo = materialId
    ? {
        pathname: "graph" as const,
        search: `?${new URLSearchParams({ material_id: materialId }).toString()}`,
      }
    : "graph";
  return (
    <nav className="subnavbar">
      <NavLink to="." end className="search notes-nav">
        Search notes
      </NavLink>
      <NavLink to="add" className="add note-nav">
        Add note
      </NavLink>
      <NavLink to={graphTo} className="graph-nav">
        Graph
      </NavLink>
    </nav>
  );
}
