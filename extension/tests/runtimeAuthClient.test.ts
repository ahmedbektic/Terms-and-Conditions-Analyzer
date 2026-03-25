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

  it("starts signed-out when auth_session is not present", async () => {
    installChromeMocks({
      auth_supabase_url: SUPABASE_URL,
      auth_supabase_anon_key: SUPABASE_ANON_KEY,
    });

    const client = new ExtensionRuntimeAuthClient();
    await expect(client.getSession()).resolves.toBeNull();
  });

  it("signs in with Google OAuth and persists auth_session", async () => {
    const { localStorageState, launchWebAuthFlowMock } = installChromeMocks({
      auth_supabase_url: SUPABASE_URL,
      auth_supabase_anon_key: SUPABASE_ANON_KEY,
    });

    const fetchMock = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/auth/v1/token?grant_type=pkce")) {
        return jsonResponse({
          access_token: "oauth-access-token",
          refresh_token: "oauth-refresh-token",
          expires_in: 3600,
          user: {
            id: "oauth-user-1",
            email: "oauth-user@example.com",
          },
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
    const launchOptions = launchWebAuthFlowMock.mock.calls[0]?.[0] as
      | chrome.identity.WebAuthFlowDetails
      | undefined;
    expect(launchOptions?.url).toContain(`${SUPABASE_URL}/auth/v1/authorize`);
    expect(launchOptions?.url).toContain("code_challenge=");
    expect(launchOptions?.url).toContain("code_challenge_method=s256");
    expect(launchOptions?.url).not.toContain("response_type=token");

    const tokenCall = fetchMock.mock.calls.find(([input]) =>
      String(input).includes("/auth/v1/token?grant_type=pkce"),
    );
    const tokenRequestInit = tokenCall?.[1] as RequestInit | undefined;
    const body = JSON.parse(String(tokenRequestInit?.body ?? "{}")) as {
      auth_code?: unknown;
      code_verifier?: unknown;
    };
    expect(body.auth_code).toBe("oauth-auth-code");
    expect(typeof body.code_verifier).toBe("string");
    expect((body.code_verifier as string).length).toBeGreaterThan(10);
  });

  it("normalizes auth/v1-style Supabase URL before building OAuth authorize URL", async () => {
    const { launchWebAuthFlowMock } = installChromeMocks({
      auth_supabase_url: `${SUPABASE_URL}/auth/v1`,
      auth_supabase_anon_key: SUPABASE_ANON_KEY,
    });

    const fetchMock = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/auth/v1/token?grant_type=pkce")) {
        return jsonResponse({
          access_token: "oauth-access-token-2",
          refresh_token: "oauth-refresh-token-2",
          expires_in: 3600,
          user: {
            id: "oauth-user-2",
            email: "oauth-user-2@example.com",
          },
        });
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    const client = new ExtensionRuntimeAuthClient();
    await client.signInWithGoogle();

    const launchOptions = launchWebAuthFlowMock.mock.calls[0]?.[0] as
      | chrome.identity.WebAuthFlowDetails
      | undefined;
    expect(launchOptions?.url).toContain(`${SUPABASE_URL}/auth/v1/authorize`);
    expect(launchOptions?.url).not.toContain("/auth/v1/auth/v1/");
  });

  it("signs in with password and persists auth_session", async () => {
    const { localStorageState } = installChromeMocks({
      auth_supabase_url: SUPABASE_URL,
      auth_supabase_anon_key: SUPABASE_ANON_KEY,
    });

    const fetchMock = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
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

  it("blocks repeated password sign-in attempts before calling Supabase again", async () => {
    installChromeMocks({
      auth_supabase_url: SUPABASE_URL,
      auth_supabase_anon_key: SUPABASE_ANON_KEY,
    });

    const fetchMock = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/auth/v1/token?grant_type=password")) {
        return jsonResponse({ message: "Invalid login credentials." }, 400);
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    const client = new ExtensionRuntimeAuthClient();
    const credentials = {
      email: "password-user@example.com",
      password: "wrong-password",
    };

    for (let attempt = 0; attempt < 5; attempt += 1) {
      await expect(client.signInWithPassword(credentials)).rejects.toThrow(
        "Invalid login credentials.",
      );
    }

    await expect(client.signInWithPassword(credentials)).rejects.toThrow(
      "Too many sign-in attempts.",
    );
    expect(fetchMock).toHaveBeenCalledTimes(5);
  });

  it("rejects invalid password credentials before calling Supabase", async () => {
    installChromeMocks({
      auth_supabase_url: SUPABASE_URL,
      auth_supabase_anon_key: SUPABASE_ANON_KEY,
    });

    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const client = new ExtensionRuntimeAuthClient();

    await expect(
      client.signInWithPassword({
        email: "bad-email",
        password: "short",
      }),
    ).rejects.toThrow("Email address is invalid.");

    expect(fetchMock).not.toHaveBeenCalled();
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

    const fetchMock = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
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
          "https://example.chromiumapp.org/supabase-auth?error=server_error&error_description=Unsupported%20provider%3A%20provider%20is%20not%20enabled",
      },
    );

    const client = new ExtensionRuntimeAuthClient();
    const expectedMessage = normalizeProviderSignInError(
      new Error("Unsupported provider: provider is not enabled"),
      AUTH_PROVIDER_GOOGLE,
    ).message;

    await expect(client.signInWithGoogle()).rejects.toThrow(expectedMessage);
  });

  it("surfaces actionable message when Chrome cannot load Google authorization page", async () => {
    installChromeMocks(
      {
        auth_supabase_url: SUPABASE_URL,
        auth_supabase_anon_key: SUPABASE_ANON_KEY,
      },
      {
        launchRuntimeErrorMessage: "Authorization page could not be loaded.",
      },
    );

    const client = new ExtensionRuntimeAuthClient();

    await expect(client.signInWithGoogle()).rejects.toThrow(
      "Google sign-in failed. Authorization page could not be loaded. Verify auth_supabase_url/EXTENSION_SUPABASE_URL is your project root URL (https://<project-ref>.supabase.co, not /auth/v1), then retry.",
    );
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
          "https://example.chromiumapp.org/supabase-auth?code=oauth-auth-code",
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
