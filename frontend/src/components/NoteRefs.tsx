import { Link } from "react-router-dom";

interface NoteTagsProps {
  tags: string[];
}

export function NoteTags({ tags }: NoteTagsProps) {
  if (!tags.length) {
    return null;
  }

  return (
    <div
      className="note-tags"
      style={{
        display: "flex",
        margin: "auto",
        flexDirection: "row",
        gap: "5px",
      }}
    >
      {tags.map((tag) => (
        <Link key={tag} className="note-tag" to={`/notes?tags_query=${encodeURIComponent(tag)}`}>
          #{tag}
        </Link>
      ))}
    </div>
  );
}

interface NoteLinkRefProps {
  linkId: string | null | undefined;
}

export function NoteLinkRef({ linkId }: NoteLinkRefProps) {
  if (!linkId) {
    return null;
  }

  return (
    <p className="note-content">
      <Link
        to={`/notes/${linkId}`}
        style={{
          textAlign: "left",
          fontSize: "2.5vh",
        }}
      >
        [[{linkId}]]
      </Link>
    </p>
  );
}
