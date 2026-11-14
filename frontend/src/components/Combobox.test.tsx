// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it } from "vitest";

import { ComboboxInput, ComboboxList, ComboboxRoot } from "./Combobox";

afterEach(() => {
  cleanup();
});

function TagsField({
  initial = [],
  maxSelected,
  sanitizeInput,
}: {
  initial?: string[];
  maxSelected?: number;
  sanitizeInput?: (raw: string) => string;
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
  it("passes the typed text through sanitizeInput", () => {
    render(<TagsField sanitizeInput={(raw) => raw.replace(/-/g, "")} />);

    expect(type("sci-fi").value).toBe("scifi");
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
});
