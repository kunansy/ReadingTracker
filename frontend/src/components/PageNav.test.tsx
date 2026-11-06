// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PageLoadError } from "./PageLoadError";
import { PageNav, type PageNavPagination } from "./PageNav";

function fakePagination(overrides: Partial<PageNavPagination> = {}): PageNavPagination {
  return {
    hasPrev: true,
    next: vi.fn(),
    prev: vi.fn(),
    order: "asc",
    toggleOrder: vi.fn(),
    ...overrides,
  };
}

afterEach(cleanup);

describe("PageNav", () => {
  it("opens the next page with the token of the response", () => {
    const pagination = fakePagination();
    render(<PageNav pagination={pagination} nextToken="token-2" />);

    fireEvent.click(screen.getByRole("button", { name: "Next »" }));

    expect(pagination.next).toHaveBeenCalledWith("token-2");
  });

  it("ignores clicks while the requested page loads", () => {
    const pagination = fakePagination();
    render(<PageNav pagination={pagination} nextToken="token-2" isBusy />);

    fireEvent.click(screen.getByRole("button", { name: "Next »" }));
    fireEvent.click(screen.getByRole("button", { name: "« Prev" }));

    expect(pagination.next).not.toHaveBeenCalled();
    expect(pagination.prev).not.toHaveBeenCalled();
  });
});

describe("PageLoadError", () => {
  it("shows the error and keeps going back to the previous page", () => {
    const pagination = fakePagination();
    render(<PageLoadError pagination={pagination} error={new Error("boom")} />);

    expect(screen.getByRole("alert").textContent).toBe("boom");
    expect(screen.getByRole("button", { name: "Next »" }).hasAttribute("disabled")).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: "« Prev" }));

    expect(pagination.prev).toHaveBeenCalledOnce();
  });
});
