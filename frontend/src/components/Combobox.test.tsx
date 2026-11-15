// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it } from "vitest";

import type { SanitizedInput } from "../tags";
import { ComboboxInput, ComboboxList, ComboboxRoot } from "./Combobox";

afterEach(() => {
  cleanup();
});

function TagsField({
  initial = [],
  maxSelected,
  sanitizeInput,
  toCreated,
}: {
  initial?: string[];
  maxSelected?: number;
  sanitizeInput?: (raw: string) => SanitizedInput;
  toCreated?: (input: string) => string;
}) {
  const [tags, setTags] = useState<string[]>(initial);
  return (
    <>
      <ComboboxRoot
        value={tags}
        onChange={setTags}
        options={[]}
        multiple
        allowCreate
        maxSelected={maxSelected}
        sanitizeInput={sanitizeInput}
        toCreated={toCreated}
      >
        <ComboboxInput placeholder="tags" />
        <ComboboxList />
      </ComboboxRoot>
      <output>{tags.join(",")}</output>
    </>
  );
}

function type(value: string) {
  const input = screen.getByPlaceholderText("tags") as HTMLInputElement;
  fireEvent.focus(input);
  fireEvent.change(input, { target: { value } });
  return input;
}

describe("Combobox", () => {
  const dropDashes = (raw: string): SanitizedInput => {
    const value = raw.replace(/-/g, "");
    return { value, notice: value === raw ? null : "dashes dropped" };
  };

  it("passes the typed text through sanitizeInput", () => {
    render(<TagsField sanitizeInput={dropDashes} />);

    expect(type("sci-fi").value).toBe("scifi");
  });

  it("shows the sanitizeInput notice and links it to the input", () => {
    render(<TagsField sanitizeInput={dropDashes} />);

    const input = type("sci-fi");

    const notice = screen.getByText("dashes dropped");
    expect(input.getAttribute("aria-describedby")).toBe(notice.id);
    expect(notice.getAttribute("aria-live")).toBe("polite");
  });

  it("clears the notice once the input is valid again", () => {
    render(<TagsField sanitizeInput={dropDashes} />);

    type("sci-fi");
    const input = type("scifix");

    expect(screen.queryByText("dashes dropped")).toBeNull();
    expect(input.hasAttribute("aria-describedby")).toBe(false);
  });

  it("clears the notice after a tag is created", () => {
    render(<TagsField sanitizeInput={dropDashes} />);

    fireEvent.keyDown(type("sci-fi"), { key: "Enter" });

    expect(screen.getByRole("status").textContent).toBe("scifi");
    expect(screen.queryByText("dashes dropped")).toBeNull();
  });

  it("creates the tag through toCreated", () => {
    render(<TagsField toCreated={(input) => input.replace(/_+$/, "")} />);

    const input = type("sci_");
    expect(screen.getByText('Create: "sci"')).toBeTruthy();
    fireEvent.keyDown(input, { key: "Enter" });

    expect(screen.getByRole("status").textContent).toBe("sci");
  });

  it("does not offer to create a tag that toCreated empties", () => {
    render(<TagsField toCreated={(input) => input.replace(/_+/g, "")} />);

    fireEvent.keyDown(type("__"), { key: "Enter" });

    expect(screen.getByRole("status").textContent).toBe("");
    expect(screen.queryByText(/^Create:/)).toBeNull();
  });

  it("keeps the typed text as is without sanitizeInput", () => {
    render(<TagsField />);

    expect(type("sci-fi").value).toBe("sci-fi");
  });

  it("creates a tag while under maxSelected", () => {
    render(<TagsField initial={["a"]} maxSelected={2} />);

    fireEvent.keyDown(type("b"), { key: "Enter" });

    expect(screen.getByRole("status").textContent).toBe("a,b");
  });

  it("does not create a tag once maxSelected is reached", () => {
    render(<TagsField initial={["a", "b"]} maxSelected={2} />);

    fireEvent.keyDown(type("c"), { key: "Enter" });

    expect(screen.getByRole("status").textContent).toBe("a,b");
    expect(screen.queryByText('Create: "c"')).toBeNull();
  });

  it("explains why nothing more can be selected once maxSelected is reached", () => {
    render(<TagsField initial={["a", "b"]} maxSelected={2} />);

    const input = type("c");
    const notice = screen.getByText("At most 2 items can be selected");

    expect(input.getAttribute("aria-describedby")).toBe(notice.id);
  });

  it("drops the maxSelected notice once an item is removed", () => {
    render(<TagsField initial={["a", "b"]} maxSelected={2} />);

    fireEvent.click(screen.getByText("b ×"));

    expect(screen.queryByText("At most 2 items can be selected")).toBeNull();
  });
});
