import { describe, expect, it } from "vitest";

import { errorResponse } from "../lib/contract";

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
});
