// @vitest-environment jsdom
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";

function LocationProbe() {
  return <span data-testid="location">{useLocation().pathname}</span>;
}

function renderAt(path: string) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <App />
      <LocationProbe />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(() => new Promise(() => {})));
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("App routes", () => {
  it("shows the not found page for an unknown path", () => {
    renderAt("/no-such-section/page");

    expect(screen.getByRole("heading", { name: "Page not found" })).toBeTruthy();
  });

  it("redirects the root path to materials", async () => {
    renderAt("/");

    await waitFor(() => {
      expect(screen.getByTestId("location").textContent).toBe("/materials/reading");
    });
  });
});
