import type { SpellError } from "../types";

type SpellErrorsListProps = {
  spellErrors: SpellError[];
  onReplace: (error: SpellError, suggestion: string) => void;
};

export function SpellErrorsList({ spellErrors, onReplace }: SpellErrorsListProps) {
  if (spellErrors.length === 0) return null;

  return (
    <div className="error" id="input-content-errata" style={{ marginTop: "4px" }}>
      {spellErrors.map((err, errorIdx) =>
        err.suggestions.length > 0 ? (
          <div key={`${err.word}-${errorIdx}`} style={{ marginBottom: "8px" }}>
            <strong>{err.word}:</strong>{" "}
            {err.suggestions.map((suggestion) => (
              <button
                key={suggestion}
                type="button"
                className="suggestion-btn"
                onClick={(e) => {
                  e.preventDefault();
                  onReplace(err, suggestion);
                }}
                style={{
                  margin: "0 4px 4px 0",
                  padding: "2px 6px",
                  background: "#fff3cd",
                  border: "1px solid #ffeaa7",
                  borderRadius: "4px",
                  cursor: "pointer",
                  fontSize: "14px",
                }}
              >
                {suggestion}
              </button>
            ))}
          </div>
        ) : (
          <div key={`${err.word}-${errorIdx}`} style={{ marginBottom: "8px" }}>
            {err.word} (исправлений нет)
          </div>
        ),
      )}
    </div>
  );
}