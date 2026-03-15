import { beforeEach, describe, expect, it, vi } from "vitest";

type DashboardApiClientConstructorArg = {
  baseUrl: string;
  getAccessToken: () => string | null;
};

const mocks = vi.hoisted(() => {
  const submitAndAnalyzeMock = vi.fn();
  // Must be constructible because production code calls `new DashboardApiClient(...)`.
  const dashboardApiClientConstructorMock = vi.fn(function (
    this: { submitAndAnalyze: typeof submitAndAnalyzeMock },
    _config: DashboardApiClientConstructorArg,
  ) {
    this.submitAndAnalyze = submitAndAnalyzeMock;
  });
  return { submitAndAnalyzeMock, dashboardApiClientConstructorMock };
});

vi.mock("../../frontend/src/lib/api/client", () => {
  return {
    DashboardApiClient: mocks.dashboardApiClientConstructorMock,
  };
});

import { analyzeExtractedTerms } from "../lib/apiClient";

describe("extension api client adapter", () => {
  beforeEach(() => {
    mocks.submitAndAnalyzeMock.mockReset();
    mocks.dashboardApiClientConstructorMock.mockClear();
  });

  it("maps extracted terms to shared report analyze payload", async () => {
    mocks.submitAndAnalyzeMock.mockResolvedValue({
      id: "report-1",
      summary: "summary",
    });

    const result = await analyzeExtractedTerms({
      baseUrl: "http://127.0.0.1:8000/api/v1",
      session: {
        userId: "user-1",
        accessToken: "token-1",
        email: null,
        expiresAt: null,
      },
      extracted: {
        terms_text: "  terms body  ",
        source_url: "https://example.com/terms",
        title: "Example Terms",
      },
    });

    expect(mocks.dashboardApiClientConstructorMock).toHaveBeenCalledTimes(1);
    const [constructorArg] = mocks.dashboardApiClientConstructorMock.mock.calls[0];
    expect(constructorArg.baseUrl).toBe("http://127.0.0.1:8000/api/v1");
    expect(constructorArg.getAccessToken()).toBe("token-1");

    expect(mocks.submitAndAnalyzeMock).toHaveBeenCalledWith({
      terms_text: "terms body",
      source_url: "https://example.com/terms",
      title: "Example Terms",
    });
    expect(result).toEqual({
      id: "report-1",
      summary: "summary",
    });
  });

  it("fails early when extracted terms text is empty", async () => {
    await expect(
      analyzeExtractedTerms({
        baseUrl: "http://127.0.0.1:8000/api/v1",
        session: {
          userId: "user-1",
          accessToken: "token-1",
          email: null,
          expiresAt: null,
        },
        extracted: {
          terms_text: "   ",
          source_url: null,
          title: null,
        },
      }),
    ).rejects.toThrow("No extracted terms text is available for analysis.");

    expect(mocks.submitAndAnalyzeMock).not.toHaveBeenCalled();
  });
});
