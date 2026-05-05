/**
 * Some Node/Vitest hosts inject `localStorage` without a working `clear()`, which breaks
 * tests that reset storage in afterEach. Replace with an in-memory Storage when needed.
 */
function ensureLocalStorageWorks(): void {
  if (typeof window === 'undefined') {
    return;
  }
  const ls = window.localStorage as Storage | undefined;
  if (ls && typeof ls.clear === 'function') {
    return;
  }

  const memory = new Map<string, string>();
  const mock: Storage = {
    get length() {
      return memory.size;
    },
    clear() {
      memory.clear();
    },
    getItem(key: string) {
      return memory.get(key) ?? null;
    },
    key(index: number) {
      return [...memory.keys()][index] ?? null;
    },
    removeItem(key: string) {
      memory.delete(key);
    },
    setItem(key: string, value: string) {
      memory.set(key, String(value));
    },
  };

  Object.defineProperty(window, 'localStorage', {
    value: mock,
    writable: true,
    configurable: true,
  });
}

ensureLocalStorageWorks();
