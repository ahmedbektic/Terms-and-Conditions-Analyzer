import type {
  AuthClient,
  AuthenticatedSession,
} from "../../../frontend/src/lib/auth/contracts";
import type { AuthAction, AuthStatePayload } from "../contract";

/**
 * Background-owned auth/session state boundary.
 *
 * Why this exists:
 * - service workers can restart between popup interactions
 * - popup/content must not become auth state authorities
 * - analysis flow needs predictable token availability
 * - session persistence is runtime-managed, not manually seeded
 *
 * The store hydrates once on startup, keeps a local cache, and still performs
 * targeted refresh reads from the auth client when session state is missing.
 */
export interface BackgroundAuthSessionStore {
  hydrate: () => Promise<void>;
  getSession: () => Promise<AuthenticatedSession | null>;
  getAuthStatePayload: () => Promise<AuthStatePayload>;
  runAuthAction: (action: AuthAction) => Promise<AuthStatePayload>;
}

export function createBackgroundAuthSessionStore(
  authClient: AuthClient,
): BackgroundAuthSessionStore {
  let cachedSession: AuthenticatedSession | null = null;
  let hydrationPromise: Promise<void> | null = null;
  let hydrated = false;

  authClient.onAuthStateChange((change) => {
    cachedSession = normalizeSession(change.session);
    hydrated = true;
  });

  return {
    hydrate,
    getSession,
    getAuthStatePayload,
    runAuthAction,
  };

  async function hydrate(): Promise<void> {
    if (hydrated) {
      return;
    }

    if (!hydrationPromise) {
      hydrationPromise = (async () => {
        await refreshSessionFromAuthClient();
        hydrated = true;
      })().finally(() => {
        hydrationPromise = null;
      });
    }

    await hydrationPromise;
  }

  async function getSession(): Promise<AuthenticatedSession | null> {
    await hydrate();

    if (cachedSession?.accessToken) {
      return cachedSession;
    }

    // If cache has no usable token, re-read from auth client so popup and
    // analysis requests see current storage-backed session state.
    return refreshSessionFromAuthClient();
  }

  async function getAuthStatePayload(): Promise<AuthStatePayload> {
    const session = await getSession();
    return toAuthStatePayload(session);
  }

  async function runAuthAction(action: AuthAction): Promise<AuthStatePayload> {
    await hydrate();
    await executeAuthAction(authClient, action);

    const session = await refreshSessionFromAuthClient();
    return toAuthStatePayload(session);
  }

  async function refreshSessionFromAuthClient(): Promise<AuthenticatedSession | null> {
    try {
      cachedSession = normalizeSession(await authClient.getSession());
      return cachedSession;
    } catch (error) {
      cachedSession = null;
      throw new Error(toSessionReadErrorMessage(error));
    }
  }
}

function normalizeSession(session: AuthenticatedSession | null | undefined): AuthenticatedSession | null {
  if (!session?.accessToken) {
    return null;
  }
  return session;
}

function toAuthStatePayload(session: AuthenticatedSession | null): AuthStatePayload {
  const authenticated = Boolean(session?.accessToken);
  return {
    authenticated,
    accessTokenPresent: authenticated,
    message: authenticated ? "Signed in." : "Not signed in.",
  };
}

function toSessionReadErrorMessage(error: unknown): string {
  const detail =
    error instanceof Error ? error.message : "Unknown auth session read failure.";
  return `Unable to load extension auth session state. ${detail}`;
}

async function executeAuthAction(authClient: AuthClient, action: AuthAction): Promise<void> {
  switch (action) {
    case "sign_in_google":
      await authClient.signInWithGoogle();
      return;
    case "sign_out":
      await authClient.signOut();
      return;
    default:
      throw new Error(`Unsupported auth action: ${String(action)}`);
  }
}
