import type { ReportAnalyzeRequest, ReportResponse } from "../../frontend/src/lib/api/contracts";
import { DashboardApiClient } from "../../frontend/src/lib/api/client";
import type { AuthenticatedSession } from "../../frontend/src/lib/auth/contracts";
import type { ExtractedTermsPayload } from "./contract";

// Extension-to-backend adapter that intentionally reuses shared web transport.

export interface AnalyzeExtractedTermsOptions {
  baseUrl: string;
  session: AuthenticatedSession;
  extracted: ExtractedTermsPayload;
  fetchImpl?: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
}

export type AnalyzeExtractedTerms = (
  options: AnalyzeExtractedTermsOptions,
) => Promise<ReportResponse>;

/**
 * Extension API adapter that reuses the shared SCRUM-11 dashboard transport seam.
 *
 * This keeps bearer-token injection and error behavior centralized in
 * `frontend/src/lib/api/client.ts`, so extension and web do not drift.
 */
export const analyzeExtractedTerms: AnalyzeExtractedTerms = async (
  options: AnalyzeExtractedTermsOptions,
): Promise<ReportResponse> => {
  const normalizedTermsText = options.extracted.terms_text.trim();
  if (!normalizedTermsText) {
    throw new Error("No extracted terms text is available for analysis.");
  }

  const payload: ReportAnalyzeRequest = {
    terms_text: normalizedTermsText,
    source_url: options.extracted.source_url ?? undefined,
    title: options.extracted.title ?? undefined,
  };

  const apiClient = new DashboardApiClient({
    baseUrl: options.baseUrl,
    getAccessToken: () => options.session.accessToken,
    fetchImpl: options.fetchImpl,
  });

  return apiClient.submitAndAnalyze(payload);
};
