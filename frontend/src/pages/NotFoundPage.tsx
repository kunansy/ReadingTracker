import { Link } from "react-router-dom";

export function NotFoundPage() {
  return (
    <div className="not-found">
      <h1>Page not found</h1>
      <p className="message">
        <Link to="/materials">Go to materials</Link>
      </p>
    </div>
  );
}
