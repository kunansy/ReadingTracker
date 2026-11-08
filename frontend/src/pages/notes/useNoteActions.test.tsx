// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiFetch } from "../../api/notes";
import { useNoteActions } from "./useNoteActions";

vi.mock("../../api/notes", () => ({ apiFetch: vi.fn() }));

const apiFetchMock = vi.mocked(apiFetch);

function setup() {
  const qc = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  const invalidate = vi.spyOn(qc, "invalidateQueries");
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  const { result } = renderHook(() => useNoteActions(), { wrapper });
  return { result, invalidate };
}

beforeEach(() => {
  apiFetchMock.mockReset();
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("useNoteActions", () => {
  it.each([
    ["deleteNote", "/n1", "DELETE"],
    ["restoreNote", "/n1/restore", "POST"],
    ["repeatNote", "/n1/repeat-queue", "POST"],
  ] as const)("%s calls the API and keeps error empty", async (action, path, method) => {
    apiFetchMock.mockResolvedValue(undefined);
    const { result } = setup();

    act(() => {
      result.current[action]("n1");
    });

    await waitFor(() => {
      expect(apiFetchMock).toHaveBeenCalledWith(path, { method });
    });
    expect(result.current.error).toBeNull();
  });

  it.each(["deleteNote", "restoreNote", "repeatNote"] as const)(
    "%s exposes the API error message",
    async (action) => {
      apiFetchMock.mockRejectedValue(new Error("NotFoundError: gone"));
      const { result } = setup();

      act(() => {
        result.current[action]("n1");
      });

      await waitFor(() => {
        expect(result.current.error).toBe("NotFoundError: gone");
      });
    },
  );

  it.each(["deleteNote", "restoreNote"] as const)(
    "%s refreshes the notes list even when it fails",
    async (action) => {
      apiFetchMock.mockRejectedValue(new Error("boom"));
      const { result, invalidate } = setup();

      act(() => {
        result.current[action]("n1");
      });

      await waitFor(() => {
        expect(invalidate).toHaveBeenCalledWith({ queryKey: ["notes"] });
      });
    },
  );

  it("clears the previous error when a new action starts", async () => {
    apiFetchMock.mockRejectedValueOnce(new Error("boom")).mockResolvedValueOnce(undefined);
    const { result } = setup();

    act(() => {
      result.current.deleteNote("n1");
    });
    await waitFor(() => {
      expect(result.current.error).toBe("boom");
    });

    act(() => {
      result.current.restoreNote("n1");
    });
    await waitFor(() => {
      expect(result.current.error).toBeNull();
    });
  });
});
