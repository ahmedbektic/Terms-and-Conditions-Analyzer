import { beforeEach, describe, expect, it, vi } from "vitest";

type RuntimeMessageListener = (
  message: unknown,
  sender: chrome.runtime.MessageSender,
  sendResponse: (response: unknown) => void,
) => boolean | void;

describe("content script extraction behavior", () => {
  let listener: RuntimeMessageListener | null = null;

  beforeEach(async () => {
    vi.resetModules();
    listener = null;
    document.body.innerHTML = "";
    document.title = "";

    (globalThis as unknown as { chrome: unknown }).chrome = {
      runtime: {
        onMessage: {
          addListener: (fn: RuntimeMessageListener) => {
            listener = fn;
          },
        },
      },
    };

    await import("../contentScript");
  });

  it("extracts from policy-focused selectors when content is long enough", async () => {
    document.title = "Policy";
    document.body.innerHTML = `<section class="terms">${"x".repeat(240)}</section>`;

    const response = await dispatch({
      type: "extraction.request",
      payload: { min_length: 200 },
    });

    expect(response).toMatchObject({
      ok: true,
      type: "extraction.result",
      payload: {
        terms_text: "x".repeat(240),
        title: "Policy",
      },
    });
  });

  it("falls back to body text when selector candidates are too short", async () => {
    document.body.innerHTML = `
      <section class="terms">short text</section>
      <main>${"body ".repeat(60)}</main>
    `;

    const response = await dispatch({
      type: "extraction.request",
      payload: { min_length: 120 },
    });

    expect(response).toMatchObject({
      ok: true,
      type: "extraction.result",
    });
    const termsText = (response as { payload: { terms_text: string } }).payload.terms_text;
    expect(termsText.length).toBeGreaterThanOrEqual(120);
    expect(termsText).toContain("body");
  });

  it("returns empty terms_text when no candidate meets minimum length", async () => {
    document.body.innerHTML = `<main>too short</main>`;

    const response = await dispatch({
      type: "extraction.request",
      payload: { min_length: 100 },
    });

    expect(response).toEqual({
      ok: true,
      type: "extraction.result",
      payload: {
        terms_text: "",
        source_url: window.location.href,
        title: document.title || null,
      },
    });
  });

  it("ignores non-extraction messages", () => {
    if (!listener) {
      throw new Error("content script listener is not registered");
    }

    const sendResponse = vi.fn();
    const handled = listener(
      { type: "analysis.request", payload: { target: "active_tab" } },
      {} as chrome.runtime.MessageSender,
      sendResponse,
    );

    expect(handled).toBe(false);
    expect(sendResponse).not.toHaveBeenCalled();
  });

  async function dispatch(request: unknown): Promise<unknown> {
    if (!listener) {
      throw new Error("content script listener is not registered");
    }
    return new Promise((resolve) => {
      listener?.(request, {} as chrome.runtime.MessageSender, (response) => {
        resolve(response);
      });
    });
  }
});
