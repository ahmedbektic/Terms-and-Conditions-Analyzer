/* Architecture note:
 * Temporary owner identity for anonymous usage.
 * This becomes optional once authenticated user tokens supply stable identity.
 */

const SESSION_STORAGE_KEY = 'terms_analyzer.session_id';

let inMemorySessionId: string | null = null;

function createSessionId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `session-${Date.now()}`;
}

export function getOrCreateSessionId(): string {
  if (typeof window === 'undefined') {
    if (!inMemorySessionId) {
      inMemorySessionId = createSessionId();
    }
    return inMemorySessionId;
  }

  const existing = window.localStorage.getItem(SESSION_STORAGE_KEY);
  if (existing) {
    return existing;
  }

  const sessionId = createSessionId();
  window.localStorage.setItem(SESSION_STORAGE_KEY, sessionId);
  return sessionId;
}
