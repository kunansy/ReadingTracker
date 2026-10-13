type Entry<T> = {
  value: T;
  expiresAt: number;
};

export function saveWithTtl<T>(key: string, value: T, ttlMs: number): void {
  const entry: Entry<T> = { value, expiresAt: Date.now() + ttlMs };
  try {
    localStorage.setItem(key, JSON.stringify(entry));
  } catch (e) {
    console.warn(`Could not save '${key}'`, e);
  }
}

export function loadWithTtl<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) {
      return null;
    }
    const entry = JSON.parse(raw) as Entry<T>;
    if (entry.expiresAt > Date.now()) {
      return entry.value;
    }
    localStorage.removeItem(key);
  } catch (e) {
    console.warn(`Could not load '${key}'`, e);
  }
  return null;
}
