import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  AUTH_PROVIDER_GOOGLE,
  normalizeProviderSignInError,
} from "../../frontend/src/lib/auth/providerErrors";

type RuntimeMessageListener = (
  message: unknown,
  sender: chrome.runtime.MessageSender,
  sendResponse: (response: unknown) => void,
) => boolean | void;

const mocks = vi.hoisted(() => {
  const authClientMock = {
    getSession: vi.fn(),
    onAuthStateChange: vi.fn(() => () => undefined),
    signInWithPassword: vi.fn(),
    signUpWithPassword: vi.fn(),
    signInWithGoogle: vi.fn(),
    signOut: vi.fn(),
  };
  const analyzeExtractedTermsMock = vi.fn();
  return { authClientMock, analyzeExtractedTermsMock };
});

vi.mock("../lib/runtimeAuthClient", () => {
  return {
    createExtensionRuntimeAuthClient: () => mocks.authClientMock,
  };
});

vi.mock("../lib/apiClient", () => {
  return {
    analyzeExtractedTerms: mocks.analyzeExtractedTermsMock,
  };
});

describe("background service worker orchestration", () => {
  let listener: RuntimeMessageListener | null = null;
  let tabsQueryMock: ReturnType<typeof vi.fn>;
  let tabsSendMessageMock: ReturnType<typeof vi.fn>;
  let storageGetMock: ReturnType<typeof vi.fn>;

  beforeEach(async () => {
    vi.clearAllMocks();
    vi.resetModules();
    listener = null;

    tabsQueryMock = vi.fn().mockResolvedValue([{ id: 11 }]);
    tabsSendMessageMock = vi.fn();
    storageGetMock = vi.fn().mockResolvedValue({});

    (globalThis as unknown as { chrome: unknown }).chrome = {
      runtime: {
        onMessage: {
          addListener: (fn: RuntimeMessageListener) => {
            listener = fn;
          },
        },
      },
      tabs: {
        query: tabsQueryMock,
        sendMessage: tabsSendMessageMock,
      },
      storage: {
        local: {
          get: storageGetMock,
        },
      },
    };

    await import("../background.service-worker");
  });

  it("returns auth state from the runtime auth adapter", async () => {
    mocks.authClientMock.getSession.mockResolvedValue(null);

    const response = await dispatch({
      type: "auth.state.request",
    });

    expect(response).toEqual({
      ok: true,
      type: "auth.state.result",
      payload: {
        authenticated: false,
        accessTokenPresent: false,
        message: "Not signed in.",
      },
    });
  });

  it("runs sign-out action through auth adapter and returns refreshed auth state", async () => {
    mocks.authClientMock.signOut.mockResolvedValue(undefined);
    mocks.authClientMock.getSession.mockResolvedValue(null);

    const response = await dispatch({
      type: "auth.action.request",
      payload: { action: "sign_out" },
    });

    expect(mocks.authClientMock.signOut).toHaveBeenCalledTimes(1);
    expect(response).toEqual({
      ok: true,
      type: "auth.action.result",
      payload: {
        action: "sign_out",
        authState: {
          authenticated: false,
          accessTokenPresent: false,
          message: "Not signed in.",
        },
      },
    });
  });

  it("orchestrates extraction then analysis for active tab requests", async () => {
    mocks.authClientMock.getSession.mockResolvedValue({
      userId: "user-1",
      accessToken: "token-1",
      email: null,
      expiresAt: null,
    });
    tabsSendMessageMock.mockResolvedValue({
      ok: true,
      type: "extraction.result",
      payload: {
        terms_text: "a".repeat(240),
        source_url: "https://example.com/terms",
        title: "Example terms",
      },
    });
    mocks.analyzeExtractedTermsMock.mockResolvedValue({
      id: "report-1",
      summary: "risk summary",
    });

    const response = await dispatch({
      type: "analysis.request",
      payload: { target: "active_tab" },
    });

    expect(tabsQueryMock).toHaveBeenCalledWith({
      active: true,
      lastFocusedWindow: true,
    });
    expect(tabsSendMessageMock).toHaveBeenCalledWith(11, {
      type: "extraction.request",
      payload: { min_length: 200 },
    });
    expect(mocks.analyzeExtractedTermsMock).toHaveBeenCalledWith({
      baseUrl: "http://127.0.0.1:8000/api/v1",
      session: {
        userId: "user-1",
        accessToken: "token-1",
        email: null,
        expiresAt: null,
      },
      extracted: {
        terms_text: "a".repeat(240),
        source_url: "https://example.com/terms",
        title: "Example terms",
      },
    });
    expect(response).toEqual({
      ok: true,
      type: "analysis.result",
      payload: {
        report_id: "report-1",
        summary: "risk summary",
      },
    });
  });

  it("returns analysis-scoped error when analysis is requested without auth session", async () => {
    mocks.authClientMock.getSession.mockResolvedValue(null);
    tabsSendMessageMock.mockResolvedValue({
      ok: true,
      type: "extraction.result",
      payload: {
        terms_text: "a".repeat(220),
        source_url: "https://example.com/terms",
        title: "Example terms",
      },
    });

    const response = await dispatch({
      type: "analysis.request",
      payload: { target: "active_tab" },
    });

    expect(response).toEqual({
      ok: false,
      type: "error",
      payload: {
        area: "analysis",
        message: "You are not signed in yet. Use extension login before running analysis.",
      },
    });
    expect(mocks.analyzeExtractedTermsMock).not.toHaveBeenCalled();
  });

  it("returns protocol error for invalid message shape", async () => {
    const response = await dispatch({
      type: "unknown.request",
    });

    expect(response).toEqual({
      ok: false,
      type: "error",
      payload: {
        area: "protocol",
        message: "Invalid popup request payload.",
      },
    });
  });

  it("returns auth-scoped error envelope when Google sign-in fails", async () => {
    const expectedMessage = normalizeProviderSignInError(
      new Error("Unsupported provider: provider is not enabled"),
      AUTH_PROVIDER_GOOGLE,
    ).message;

    mocks.authClientMock.signInWithGoogle.mockRejectedValueOnce(new Error(expectedMessage));

    const response = await dispatch({
      type: "auth.action.request",
      payload: { action: "sign_in_google" },
    });

    expect(response).toEqual({
      ok: false,
      type: "error",
      payload: {
        area: "auth",
        message: expectedMessage,
      },
    });
  });

  async function dispatch(request: unknown): Promise<unknown> {
    if (!listener) {
      throw new Error("background message listener is not registered");
    }
    return new Promise((resolve) => {
      listener?.(request, {} as chrome.runtime.MessageSender, (response) => {
        resolve(response);
      });
    });
  }
});
