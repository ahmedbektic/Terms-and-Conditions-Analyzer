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
