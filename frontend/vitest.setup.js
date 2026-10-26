// api.js reads/writes localStorage at import time (session token) and on
// logout. Tests run under the plain "node" vitest environment (no jsdom —
// jsdom's fetch polyfill pulls in undici versions that break across Node
// versions), so provide a minimal in-memory stand-in instead.
if (typeof globalThis.localStorage === "undefined") {
  const store = new Map();
  globalThis.localStorage = {
    getItem: (key) => (store.has(key) ? store.get(key) : null),
    setItem: (key, value) => store.set(key, String(value)),
    removeItem: (key) => store.delete(key),
    clear: () => store.clear(),
  };
}
