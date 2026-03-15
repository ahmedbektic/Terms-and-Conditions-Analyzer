import { describe, expect, it } from "vitest";

import { errorResponse, isPopupToBackgroundMessage } from "../lib/contract";

describe("extension message contract helpers", () => {
  it("creates a typed error envelope with area and message", () => {
    const response = errorResponse("analysis", "analysis failed");

    expect(response).toEqual({
      ok: false,
      type: "error",
      payload: {
        area: "analysis",
        message: "analysis failed",
      },
    });
  });

  it("accepts valid popup->background messages", () => {
    expect(isPopupToBackgroundMessage({ type: "auth.state.request" })).toBe(true);
    expect(
      isPopupToBackgroundMessage({
        type: "auth.action.request",
        payload: { action: "sign_in_google" },
      }),
    ).toBe(true);
    expect(
      isPopupToBackgroundMessage({
        type: "auth.action.request",
        payload: { action: "sign_out" },
      }),
    ).toBe(true);
    expect(
      isPopupToBackgroundMessage({
        type: "analysis.request",
        payload: { target: "active_tab" },
      }),
    ).toBe(true);
  });

  it("rejects malformed popup->background messages", () => {
    expect(isPopupToBackgroundMessage({ type: "analysis.request", payload: {} })).toBe(
      false,
    );
    expect(
      isPopupToBackgroundMessage({
        type: "auth.action.request",
        payload: { action: "sign_in_password" },
      }),
    ).toBe(false);
    expect(isPopupToBackgroundMessage({ type: "unknown.request" })).toBe(false);
    expect(isPopupToBackgroundMessage(null)).toBe(false);
  });
});
