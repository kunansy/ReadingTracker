type Entry = {
  value: unknown;
  expiresAt: number;
};

function isEntry(parsed: unknown): parsed is Entry {
  return (
    typeof parsed === "object" &&
    parsed !== null &&
    "value" in parsed &&
    "expiresAt" in parsed &&
    typeof parsed.expiresAt === "number"
  );
}

function parseEntry(raw: string): Entry | null {
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }
  return isEntry(parsed) ? parsed : null;
}

export function saveWithTtl<T>(key: string, value: T, ttlMs: number): void {
  const entry: Entry = { value, expiresAt: Date.now() + ttlMs };
  try {
    localStorage.setItem(key, JSON.stringify(entry));
  } catch (e) {
    console.warn(`Could not save '${key}'`, e);
  }
}

// The stored value is not validated: the caller must narrow it before use.
export function loadWithTtl(key: string): unknown {
  try {
    const raw = localStorage.getItem(key);
    if (raw === null) {
      return null;
    }
    const entry = parseEntry(raw);
    if (entry !== null && entry.expiresAt > Date.now()) {
      return entry.value;
    }
    localStorage.removeItem(key);
  } catch (e) {
    console.warn(`Could not load '${key}'`, e);
  }
  return null;
}
