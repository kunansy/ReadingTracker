// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";

import { NoteLinkRef, NoteTags } from "./NoteRefs";

afterEach(() => {
  cleanup();
});

function renderInRouter(node: React.ReactNode) {
  return render(<MemoryRouter>{node}</MemoryRouter>);
}

describe("NoteTags", () => {
  it("renders nothing without tags", () => {
    const { container } = renderInRouter(<NoteTags tags={[]} />);

    expect(container.innerHTML).toBe("");
  });

  it("renders every tag as a search link in the given order", () => {
    renderInRouter(<NoteTags tags={["b", "тег", "a"]} />);

    const links = screen.getAllByRole("link");
    expect(links.map((link) => link.textContent)).toEqual(["#b", "#тег", "#a"]);
    expect(links.map((link) => link.getAttribute("href"))).toEqual([
      "/notes?tags_query=b",
      `/notes?tags_query=${encodeURIComponent("тег")}`,
      "/notes?tags_query=a",
    ]);
  });
});

describe("NoteLinkRef", () => {
  it.each([null, undefined, ""])("renders nothing for linkId=%j", (linkId) => {
    const { container } = renderInRouter(<NoteLinkRef linkId={linkId} />);

    expect(container.innerHTML).toBe("");
  });

  it("renders the linked note as an in-app link marked with its id", () => {
    renderInRouter(<NoteLinkRef linkId="note-1" />);

    const link = screen.getByRole("link", { name: "[[note-1]]" });
    expect(link.getAttribute("href")).toBe("/notes/note-1");
    expect(link.closest("p")?.dataset.linkId).toBe("note-1");
  });
});
