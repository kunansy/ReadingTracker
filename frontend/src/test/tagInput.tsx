import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { expect, vi } from "vitest";

import { TAGS_MAX_ITEMS } from "../api/constraints";
import { TAG_SEPARATOR_NOTICE } from "../tags";

const TAGS_PLACEHOLDER = "Enter tags";

export const FULL_TAGS: readonly string[] = Array.from(
  { length: TAGS_MAX_ITEMS },
  (_, i) => `t${String(i).padStart(2, "0")}`,
);

export function json(status: number, body: unknown): Promise<Response> {
  return Promise.resolve(
    new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }),
  );
}

export function stubGetRoutes(routes: Readonly<Record<string, unknown>>): void {
  vi.stubGlobal(
    "fetch",
    vi.fn((request: Request) => {
      const path = new URL(request.url).pathname;
      if (request.method === "GET" && path in routes) {
        return json(200, routes[path]);
      }
      return json(404, { detail: `unexpected ${request.method} ${path}` });
    }),
  );
}

export function renderPage(page: ReactElement, url: string): void {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <MemoryRouter initialEntries={[url]}>
      <QueryClientProvider client={qc}>{page}</QueryClientProvider>
    </MemoryRouter>,
  );
}

export async function typeTag(value: string): Promise<HTMLInputElement> {
  const input = (await screen.findByPlaceholderText(TAGS_PLACEHOLDER)) as HTMLInputElement;
  fireEvent.focus(input);
  fireEvent.change(input, { target: { value } });
  return input;
}

export async function addTags(tags: readonly string[]): Promise<void> {
  for (const tag of tags) {
    fireEvent.keyDown(await typeTag(tag), { key: "Enter" });
  }
}

export async function expectTagInputIsSanitized(): Promise<void> {
  const input = await typeTag("Sci-Fi");

  expect(input.value).toBe("sci_fi");
  expect(screen.getByText(TAG_SEPARATOR_NOTICE)).not.toBeNull();
  expect(screen.getByText('Create: "sci_fi"')).not.toBeNull();

  expect((await typeTag("c++")).value).toBe("c_");
  expect(screen.getByText('Create: "c"')).not.toBeNull();
}

export async function expectNoTagIsCreatedOnceFull(): Promise<void> {
  for (const tag of FULL_TAGS) {
    expect(await screen.findByText(`${tag} ×`)).not.toBeNull();
  }

  fireEvent.keyDown(await typeTag("extra"), { key: "Enter" });

  expect(screen.queryByText('Create: "extra"')).toBeNull();
  expect(screen.queryByText("extra ×")).toBeNull();
}
