import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

type SendMessageHandler = (request: unknown) => unknown;

describe("popup flow", () => {
  let sendMessageHandler: SendMessageHandler;
  let sendMessageMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.resetModules();
    document.body.innerHTML = `
      <div id="status">Loading...</div>
      <button id="loginBtn" class="hidden">Log in</button>
      <button id="logoutBtn" class="hidden">Log out</button>
      <button id="analyzeBtn" class="hidden">Analyze page</button>
      <pre id="output"></pre>
    `;

    sendMessageHandler = () => ({
      ok: false,
      type: "error",
      payload: { area: "protocol", message: "No handler configured." },
    });

    sendMessageMock = vi.fn((request: unknown, callback: (response: unknown) => void) => {
      callback(sendMessageHandler(request));
    });

    (globalThis as unknown as { chrome: unknown }).chrome = {
      runtime: {
        sendMessage: sendMessageMock,
      },
    };
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("loads auth state from background and shows signed-out controls", async () => {
    sendMessageHandler = (request) => {
      if (isAuthStateRequest(request)) {
        return {
          ok: true,
          type: "auth.state.result",
          payload: {
            authenticated: false,
            accessTokenPresent: false,
            message: "Not signed in.",
          },
        };
      }
      return unexpected(request);
    };

    await import("../popup/index");
    await flushAsync();

    expect(text("status")).toBe("Not signed in.");
    expect(hasHiddenClass("loginBtn")).toBe(false);
    expect(hasHiddenClass("logoutBtn")).toBe(true);
    expect(hasHiddenClass("analyzeBtn")).toBe(true);
  });

  it("runs login action through background and shows analysis-ready controls", async () => {
    sendMessageHandler = (request) => {
      if (isAuthStateRequest(request)) {
        return {
          ok: true,
          type: "auth.state.result",
          payload: {
            authenticated: false,
            accessTokenPresent: false,
            message: "Not signed in.",
          },
        };
      }
      if (isAuthActionRequest(request, "sign_in_google")) {
        return {
          ok: true,
          type: "auth.action.result",
          payload: {
            action: "sign_in_google",
            authState: {
              authenticated: true,
              accessTokenPresent: true,
              message: "Signed in.",
            },
          },
        };
      }
      return unexpected(request);
    };

    await import("../popup/index");
    await flushAsync();

    click("loginBtn");
    await flushAsync();

    expect(text("status")).toBe("Signed in.");
    expect(hasHiddenClass("loginBtn")).toBe(true);
    expect(hasHiddenClass("logoutBtn")).toBe(false);
    expect(hasHiddenClass("analyzeBtn")).toBe(false);
  });

  it("supports runtime SCRUM-9 popup path from signed-out to analysis result", async () => {
    let authStateRequestCount = 0;

    sendMessageHandler = (request) => {
      if (isAuthStateRequest(request)) {
        authStateRequestCount += 1;
        return {
          ok: true,
          type: "auth.state.result",
          payload: {
            authenticated: false,
            accessTokenPresent: false,
            message: "Not signed in.",
          },
        };
      }

      if (isAuthActionRequest(request, "sign_in_google")) {
        return {
          ok: true,
          type: "auth.action.result",
          payload: {
            action: "sign_in_google",
            authState: {
              authenticated: true,
              accessTokenPresent: true,
              message: "Signed in.",
            },
          },
        };
      }

      if (isAnalysisRequest(request)) {
        return {
          ok: true,
          type: "analysis.result",
          payload: {
            report_id: "report-runtime",
            summary: "Runtime sign-in flow summary.",
          },
        };
      }

      return unexpected(request);
    };

    await import("../popup/index");
    await flushAsync();

    expect(authStateRequestCount).toBe(1);
    expect(text("status")).toBe("Not signed in.");

    click("loginBtn");
    await flushAsync();

    expect(text("status")).toBe("Signed in.");
    expect(hasHiddenClass("analyzeBtn")).toBe(false);

    click("analyzeBtn");
    await flushAsync();

    expect(text("status")).toBe("Analysis complete.");
    expect(text("output")).toBe("Runtime sign-in flow summary.");
  });

  it("shows auth-scoped error and keeps unauthenticated controls when login fails", async () => {
    sendMessageHandler = (request) => {
      if (isAuthStateRequest(request)) {
        return {
          ok: true,
          type: "auth.state.result",
          payload: {
            authenticated: false,
            accessTokenPresent: false,
            message: "Not signed in.",
          },
        };
      }
      if (isAuthActionRequest(request, "sign_in_google")) {
        return {
          ok: false,
          type: "error",
          payload: {
            area: "auth",
            message: "Google sign-in is not enabled for this environment.",
          },
        };
      }
      return unexpected(request);
    };

    await import("../popup/index");
    await flushAsync();

    click("loginBtn");
    await flushAsync();

    expect(text("status")).toBe("[auth] Google sign-in is not enabled for this environment.");
    expect(hasHiddenClass("loginBtn")).toBe(false);
    expect(hasHiddenClass("logoutBtn")).toBe(true);
    expect(hasHiddenClass("analyzeBtn")).toBe(true);
  });

  it("handles analysis request via background and renders summary", async () => {
    sendMessageHandler = (request) => {
      if (isAuthStateRequest(request)) {
        return {
          ok: true,
          type: "auth.state.result",
          payload: {
            authenticated: true,
            accessTokenPresent: true,
            message: "Signed in.",
          },
        };
      }
      if (isAnalysisRequest(request)) {
        return {
          ok: true,
          type: "analysis.result",
          payload: {
            report_id: "report-1",
            summary: "Risk summary.",
          },
        };
      }
      return unexpected(request);
    };

    await import("../popup/index");
    await flushAsync();

    click("analyzeBtn");
    await flushAsync();

    expect(text("status")).toBe("Analysis complete.");
    expect(text("output")).toBe("Risk summary.");
    expect(hasHiddenClass("logoutBtn")).toBe(false);
  });

  it("runs logout action through background and returns to signed-out controls", async () => {
    sendMessageHandler = (request) => {
      if (isAuthStateRequest(request)) {
        return {
          ok: true,
          type: "auth.state.result",
          payload: {
            authenticated: true,
            accessTokenPresent: true,
            message: "Signed in.",
          },
        };
      }
      if (isAuthActionRequest(request, "sign_out")) {
        return {
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
        };
      }
      return unexpected(request);
    };

    await import("../popup/index");
    await flushAsync();

    click("logoutBtn");
    await flushAsync();

    expect(text("status")).toBe("Not signed in.");
    expect(hasHiddenClass("loginBtn")).toBe(false);
    expect(hasHiddenClass("logoutBtn")).toBe(true);
    expect(hasHiddenClass("analyzeBtn")).toBe(true);
  });

  it("shows structured error message returned from background", async () => {
    sendMessageHandler = (request) => {
      if (isAuthStateRequest(request)) {
        return {
          ok: true,
          type: "auth.state.result",
          payload: {
            authenticated: true,
            accessTokenPresent: true,
            message: "Signed in.",
          },
        };
      }
      if (isAnalysisRequest(request)) {
        return {
          ok: false,
          type: "error",
          payload: {
            area: "analysis",
            message: "No extractable terms text was found on the active page.",
          },
        };
      }
      return unexpected(request);
    };

    await import("../popup/index");
    await flushAsync();

    click("analyzeBtn");
    await flushAsync();

    expect(text("status")).toBe(
      "[analysis] No extractable terms text was found on the active page.",
    );
  });
});

function unexpected(request: unknown) {
  return {
    ok: false,
    type: "error",
    payload: {
      area: "protocol",
      message: `Unexpected request: ${JSON.stringify(request)}`,
    },
  };
}

function isAuthStateRequest(request: unknown): request is { type: "auth.state.request" } {
  return (
    typeof request === "object" &&
    request !== null &&
    (request as { type?: unknown }).type === "auth.state.request"
  );
}

function isAnalysisRequest(request: unknown): request is {
  type: "analysis.request";
  payload: { target: "active_tab" };
} {
  if (typeof request !== "object" || request === null) {
    return false;
  }
  const typed = request as { type?: unknown; payload?: { target?: unknown } };
  return typed.type === "analysis.request" && typed.payload?.target === "active_tab";
}

function isAuthActionRequest(
  request: unknown,
  action: "sign_in_google" | "sign_out",
): request is {
  type: "auth.action.request";
  payload: { action: "sign_in_google" | "sign_out" };
} {
  if (typeof request !== "object" || request === null) {
    return false;
  }

  const typed = request as { type?: unknown; payload?: { action?: unknown } };
  return typed.type === "auth.action.request" && typed.payload?.action === action;
}

function click(id: string): void {
  const element = document.getElementById(id) as HTMLButtonElement | null;
  if (!element) {
    throw new Error(`Missing element: ${id}`);
  }
  element.click();
}

function text(id: string): string {
  const element = document.getElementById(id) as HTMLElement | null;
  if (!element) {
    throw new Error(`Missing element: ${id}`);
  }
  return element.textContent ?? "";
}

function hasHiddenClass(id: string): boolean {
  const element = document.getElementById(id) as HTMLElement | null;
  if (!element) {
    throw new Error(`Missing element: ${id}`);
  }
  return element.classList.contains("hidden");
}

async function flushAsync(): Promise<void> {
  await Promise.resolve();
  await Promise.resolve();
}
