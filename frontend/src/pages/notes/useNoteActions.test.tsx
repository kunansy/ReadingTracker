// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { unwrap } from "../../api/client";
import { useNoteActions } from "./useNoteActions";

vi.mock("../../api/client", () => ({
  api: {
    DELETE: (path: string, init: unknown) => ({ method: "DELETE", path, init }),
    POST: (path: string, init: unknown) => ({ method: "POST", path, init }),
  },
  unwrap: vi.fn(),
}));

const unwrapMock = vi.mocked(unwrap);

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
  unwrapMock.mockReset();
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("useNoteActions", () => {
  it.each([
    ["deleteNote", "/api/v1/notes/{note_id}", "DELETE"],
    ["restoreNote", "/api/v1/notes/{note_id}/restore", "POST"],
    ["repeatNote", "/api/v1/notes/{note_id}/repeat-queue", "POST"],
  ] as const)("%s calls the API and keeps error empty", async (action, path, method) => {
    unwrapMock.mockResolvedValue(undefined);
    const { result } = setup();

    act(() => {
      result.current[action]("n1");
    });

    await waitFor(() => {
      expect(unwrapMock).toHaveBeenCalledWith({
        method,
        path,
        init: { params: { path: { note_id: "n1" } } },
      });
    });
    expect(result.current.error).toBeNull();
  });

  it.each(["deleteNote", "restoreNote", "repeatNote"] as const)(
    "%s exposes the API error message",
    async (action) => {
      unwrapMock.mockRejectedValue(new Error("NotFoundError: gone"));
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
      unwrapMock.mockRejectedValue(new Error("boom"));
      const { result, invalidate } = setup();

      act(() => {
        result.current[action]("n1");
      });

      await waitFor(() => {
        expect(invalidate).toHaveBeenCalledWith({ queryKey: ["notes"] });
      });
    },
  );

  it("clears the error when a later action succeeds", async () => {
    unwrapMock.mockRejectedValueOnce(new Error("boom")).mockResolvedValueOnce(undefined);
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

  it("keeps the error visible while a later action is still running", async () => {
    unwrapMock
      .mockRejectedValueOnce(new Error("boom"))
      .mockReturnValueOnce(new Promise(() => {}));
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
      expect(unwrapMock).toHaveBeenCalledTimes(2);
    });
    expect(result.current.error).toBe("boom");
  });

  it("keeps the error of an earlier action that fails after a later success", async () => {
    let rejectDelete: (err: Error) => void = () => {};
    unwrapMock
      .mockReturnValueOnce(
        new Promise((_, reject) => {
          rejectDelete = reject;
        }),
      )
      .mockResolvedValueOnce(undefined);
    const { result } = setup();

    act(() => {
      result.current.deleteNote("n1");
    });
    act(() => {
      result.current.restoreNote("n2");
    });
    await waitFor(() => {
      expect(unwrapMock).toHaveBeenCalledTimes(2);
    });

    act(() => {
      rejectDelete(new Error("delete failed"));
    });
    await waitFor(() => {
      expect(result.current.error).toBe("delete failed");
    });
  });

  it("dismissError clears the error", async () => {
    unwrapMock.mockRejectedValueOnce(new Error("boom"));
    const { result } = setup();

    act(() => {
      result.current.deleteNote("n1");
    });
    await waitFor(() => {
      expect(result.current.error).toBe("boom");
    });

    act(() => {
      result.current.dismissError();
    });
    expect(result.current.error).toBeNull();
  });

  it("repeatNote does not refresh the notes list", async () => {
    unwrapMock.mockResolvedValue(undefined);
    const { result, invalidate } = setup();

    act(() => {
      result.current.repeatNote("n1");
    });
    await waitFor(() => {
      expect(unwrapMock).toHaveBeenCalledTimes(1);
    });

    expect(invalidate).not.toHaveBeenCalled();
  });
});
