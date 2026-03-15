import { describe, expect, it, vi } from "vitest";

import type {
  AuthClient,
  AuthStateChange,
  AuthenticatedSession,
} from "../../frontend/src/lib/auth/contracts";
import { createBackgroundAuthSessionStore } from "../lib/background/authSessionStore";

describe("background auth session store", () => {
  it("hydrates cached session on startup and serves auth state from cache", async () => {
    const harness = createAuthClientHarness();
    harness.getSessionMock.mockResolvedValue({
      userId: "user-1",
      accessToken: "token-1",
      email: "user@example.com",
      expiresAt: null,
    });

    const store = createBackgroundAuthSessionStore(harness.client);
    await store.hydrate();

    expect(harness.getSessionMock).toHaveBeenCalledTimes(1);

    const authState = await store.getAuthStatePayload();
    expect(authState).toEqual({
      authenticated: true,
      accessTokenPresent: true,
      message: "Signed in.",
    });
    expect(harness.getSessionMock).toHaveBeenCalledTimes(1);
  });

  it("refreshes session from auth client when cache has no token", async () => {
    const harness = createAuthClientHarness();
    harness.getSessionMock
      .mockResolvedValueOnce(null)
      .mockResolvedValueOnce({
        userId: "user-2",
        accessToken: "token-2",
        email: "user2@example.com",
        expiresAt: null,
      });

    const store = createBackgroundAuthSessionStore(harness.client);
    await store.hydrate();
    const session = await store.getSession();

    expect(session).toMatchObject({
      userId: "user-2",
      accessToken: "token-2",
    });
    expect(harness.getSessionMock).toHaveBeenCalledTimes(2);
  });

  it("runs sign-out action and returns signed-out state", async () => {
    const harness = createAuthClientHarness();
    harness.getSessionMock
      .mockResolvedValueOnce({
        userId: "user-3",
        accessToken: "token-3",
        email: "user3@example.com",
        expiresAt: null,
      })
      .mockResolvedValueOnce(null);
    harness.signOutMock.mockResolvedValue(undefined);

    const store = createBackgroundAuthSessionStore(harness.client);
    await store.hydrate();
    const authState = await store.runAuthAction("sign_out");

    expect(harness.signOutMock).toHaveBeenCalledTimes(1);
    expect(authState).toEqual({
      authenticated: false,
      accessTokenPresent: false,
      message: "Not signed in.",
    });
  });
});

interface AuthClientHarness {
  client: AuthClient;
  getSessionMock: ReturnType<typeof vi.fn<() => Promise<AuthenticatedSession | null>>>;
  signOutMock: ReturnType<typeof vi.fn<() => Promise<void>>>;
}

function createAuthClientHarness(): AuthClientHarness {
  const getSessionMock = vi.fn<() => Promise<AuthenticatedSession | null>>();
  const signOutMock = vi.fn<() => Promise<void>>();
  const onAuthStateChangeMock = vi.fn(
    (_listener: (change: AuthStateChange) => void) => () => undefined,
  );

  const client: AuthClient = {
    getSession: getSessionMock,
    onAuthStateChange: onAuthStateChangeMock,
    signInWithPassword: async () => undefined,
    signUpWithPassword: async () => undefined,
    signInWithGoogle: async () => undefined,
    signOut: signOutMock,
  };

  return {
    client,
    getSessionMock,
    signOutMock,
  };
}
