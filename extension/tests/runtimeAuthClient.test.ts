import { beforeEach, describe, expect, it, vi } from "vitest";

import { ExtensionRuntimeAuthClient } from "../lib/runtimeAuthClient";
import {
  AUTH_PROVIDER_GOOGLE,
  normalizeProviderSignInError,
} from "../../frontend/src/lib/auth/providerErrors";

const SUPABASE_URL = "https://project-ref.supabase.co";
const SUPABASE_ANON_KEY = "anon-key";

describe("extension runtime auth client", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("signs in with Google OAuth and persists auth_session", async () => {
    const { localStorageState } = installChromeMocks({
      auth_supabase_url: SUPABASE_URL,
      auth_supabase_anon_key: SUPABASE_ANON_KEY,
    });

    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/auth/v1/user")) {
        return jsonResponse({
          id: "oauth-user-1",
          email: "oauth-user@example.com",
        });
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    const client = new ExtensionRuntimeAuthClient();
    await client.signInWithGoogle();

    expect(localStorageState.auth_session).toMatchObject({
      userId: "oauth-user-1",
      accessToken: "oauth-access-token",
      email: "oauth-user@example.com",
    });
    expect(localStorageState.auth_refresh_token).toBe("oauth-refresh-token");
  });

  it("signs in with password and persists auth_session", async () => {
    const { localStorageState } = installChromeMocks({
      auth_supabase_url: SUPABASE_URL,
      auth_supabase_anon_key: SUPABASE_ANON_KEY,
    });

    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/auth/v1/token?grant_type=password")) {
        return jsonResponse({
          access_token: "password-access-token",
          refresh_token: "password-refresh-token",
          expires_in: 3600,
          user: {
            id: "password-user-1",
            email: "password-user@example.com",
          },
        });
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    const client = new ExtensionRuntimeAuthClient();
    await client.signInWithPassword({
      email: "password-user@example.com",
      password: "strong-password",
    });

    expect(localStorageState.auth_session).toMatchObject({
      userId: "password-user-1",
      accessToken: "password-access-token",
      email: "password-user@example.com",
    });
    expect(localStorageState.auth_refresh_token).toBe("password-refresh-token");
  });

  it("clears local auth_session on signOut even if provider logout fails", async () => {
    const { localStorageState } = installChromeMocks({
      auth_supabase_url: SUPABASE_URL,
      auth_supabase_anon_key: SUPABASE_ANON_KEY,
      auth_session: {
        userId: "signed-in-user",
        accessToken: "signed-in-token",
        email: "signed-in@example.com",
        expiresAt: null,
      },
      auth_refresh_token: "refresh-token",
    });

    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/auth/v1/logout")) {
        return jsonResponse({ message: "logout failed" }, 500);
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    const client = new ExtensionRuntimeAuthClient();
    await client.signOut();

    expect(localStorageState.auth_session).toBeUndefined();
    expect(localStorageState.auth_refresh_token).toBeUndefined();
  });

  it("maps provider-disabled OAuth callback errors to normalized message", async () => {
    installChromeMocks(
      {
        auth_supabase_url: SUPABASE_URL,
        auth_supabase_anon_key: SUPABASE_ANON_KEY,
      },
      {
        oauthCallbackUrl:
          "https://example.chromiumapp.org/supabase-auth#error=server_error&error_description=Unsupported%20provider%3A%20provider%20is%20not%20enabled",
      },
    );

    const client = new ExtensionRuntimeAuthClient();
    const expectedMessage = normalizeProviderSignInError(
      new Error("Unsupported provider: provider is not enabled"),
      AUTH_PROVIDER_GOOGLE,
    ).message;

    await expect(client.signInWithGoogle()).rejects.toThrow(expectedMessage);
  });
});

interface ChromeMockOptions {
  oauthCallbackUrl?: string;
  launchRuntimeErrorMessage?: string;
}

function installChromeMocks(
  initialState: Record<string, unknown>,
  options: ChromeMockOptions = {},
) {
  const localStorageState: Record<string, unknown> = { ...initialState };
  const runtime: {
    lastError?: chrome.runtime.LastError;
  } = {
    lastError: undefined,
  };

  const getMock = vi.fn(
    async (keys?: string | string[] | Record<string, unknown>): Promise<Record<string, unknown>> => {
      if (!keys) {
        return { ...localStorageState };
      }

      if (typeof keys === "string") {
        return { [keys]: localStorageState[keys] };
      }

      if (Array.isArray(keys)) {
        return keys.reduce<Record<string, unknown>>((accumulator, key) => {
          accumulator[key] = localStorageState[key];
          return accumulator;
        }, {});
      }

      const output: Record<string, unknown> = {};
      for (const [key, defaultValue] of Object.entries(keys)) {
        output[key] = key in localStorageState ? localStorageState[key] : defaultValue;
      }
      return output;
    },
  );

  const setMock = vi.fn(async (items: Record<string, unknown>) => {
    Object.assign(localStorageState, items);
  });

  const removeMock = vi.fn(async (keys: string | string[]) => {
    const keysToRemove = Array.isArray(keys) ? keys : [keys];
    for (const key of keysToRemove) {
      delete localStorageState[key];
    }
  });

  const launchWebAuthFlowMock = vi.fn(
    (
      _details: chrome.identity.WebAuthFlowDetails,
      callback?: (responseUrl?: string) => void,
    ) => {
      if (options.launchRuntimeErrorMessage) {
        runtime.lastError = { message: options.launchRuntimeErrorMessage };
        callback?.();
        runtime.lastError = undefined;
        return;
      }

      runtime.lastError = undefined;
      callback?.(
        options.oauthCallbackUrl ??
          "https://example.chromiumapp.org/supabase-auth#access_token=oauth-access-token&refresh_token=oauth-refresh-token&expires_in=3600",
      );
    },
  );

  (globalThis as unknown as { chrome: unknown }).chrome = {
    runtime,
    storage: {
      local: {
        get: getMock,
        set: setMock,
        remove: removeMock,
      },
      onChanged: {
        addListener: vi.fn(),
        removeListener: vi.fn(),
      },
    },
    identity: {
      getRedirectURL: vi.fn(() => "https://example.chromiumapp.org/supabase-auth"),
      launchWebAuthFlow: launchWebAuthFlowMock,
    },
  } as unknown as typeof chrome;

  return {
    localStorageState,
    getMock,
    setMock,
    removeMock,
    launchWebAuthFlowMock,
  };
}

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      "Content-Type": "application/json",
    },
  });
}
