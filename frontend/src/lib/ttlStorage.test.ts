import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { loadWithTtl, saveWithTtl } from "./ttlStorage.ts";

const KEY = "test-key";
const TTL_MS = 1000;
const NOW = new Date(2025, 0, 15, 12).getTime();

function createFakeStorage(initial: Record<string, string> = {}) {
  const items = new Map(Object.entries(initial));
  return {
    getItem: (key: string) => items.get(key) ?? null,
    setItem: (key: string, value: string) => {
      items.set(key, value);
    },
    removeItem: (key: string) => {
      items.delete(key);
    },
    has: (key: string) => items.has(key),
  };
}

describe("ttlStorage", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(NOW);
    vi.spyOn(console, "warn").mockImplementation(() => {});
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  test("returns the saved value before it expires", () => {
    vi.stubGlobal("localStorage", createFakeStorage());
    saveWithTtl(KEY, { chapter: "3", page: 42 }, TTL_MS);
    vi.setSystemTime(NOW + TTL_MS - 1);

    expect(loadWithTtl(KEY)).toEqual({ chapter: "3", page: 42 });
  });

  test("returns null when nothing is stored", () => {
    vi.stubGlobal("localStorage", createFakeStorage());

    expect(loadWithTtl(KEY)).toBeNull();
  });

  test("returns null and removes the entry once it has expired", () => {
    const storage = createFakeStorage();
    vi.stubGlobal("localStorage", storage);
    saveWithTtl(KEY, "value", TTL_MS);
    vi.setSystemTime(NOW + TTL_MS + 1);

    expect(loadWithTtl(KEY)).toBeNull();
    expect(storage.has(KEY)).toBe(false);
  });

  test("treats an entry as expired exactly at its expiry time", () => {
    vi.stubGlobal("localStorage", createFakeStorage());
    saveWithTtl(KEY, "value", TTL_MS);
    vi.setSystemTime(NOW + TTL_MS);

    expect(loadWithTtl(KEY)).toBeNull();
  });

  test.each([
    ["corrupt JSON", "{not json"],
    ["JSON null", "null"],
    ["a non-object", "42"],
    ["an entry without expiresAt", JSON.stringify({ value: "value" })],
    ["a non-numeric expiresAt", JSON.stringify({ value: "value", expiresAt: "tomorrow" })],
    ["an entry without value", JSON.stringify({ expiresAt: NOW + TTL_MS })],
  ])("returns null and removes %s", (_name, raw) => {
    const storage = createFakeStorage({ [KEY]: raw });
    vi.stubGlobal("localStorage", storage);

    expect(loadWithTtl(KEY)).toBeNull();
    expect(storage.has(KEY)).toBe(false);
  });

  test("returns null when reading from storage throws", () => {
    vi.stubGlobal("localStorage", {
      ...createFakeStorage(),
      getItem: () => {
        throw new Error("storage is blocked");
      },
    });

    expect(loadWithTtl(KEY)).toBeNull();
  });

  test("does not throw when writing to storage fails", () => {
    vi.stubGlobal("localStorage", {
      ...createFakeStorage(),
      setItem: () => {
        throw new Error("quota exceeded");
      },
    });

    expect(() => saveWithTtl(KEY, "value", TTL_MS)).not.toThrow();
  });
});
