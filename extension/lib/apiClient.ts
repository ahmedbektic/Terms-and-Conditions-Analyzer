// extension/lib/apiClient.ts
// Pure API client for the extension.
// It is stateless and requires the access token to be passed on every request.
// The client aligns with the backend's existing REST contracts.

import { AnalysisResponsePayload, AnalysisRequestPayload } from "./contract";

export interface BackendApiConfig {
  /**
   * Base URL of the backend API (e.g., https://api.yourdomain.com).
   */
  baseUrl: string;
}

/**
 * Factory that creates an API client.
 * The returned object contains methods for the supported backend endpoints.
 */
export function createClient(config: BackendApiConfig) {
  // Ensure baseUrl has no trailing slash for consistency.
  const base = config.baseUrl.replace(/\/$/, "");

  const request = async <T>(method: string, path: string, body: any, token?: string): Promise<T> => {
    const url = `${base}${path}`;
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
    if (token) headers.Authorization = `Bearer ${token}`;
    const res = await fetch(url, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`API error ${res.status}: ${text}`);
    }
    return res.json() as Promise<T>;
  };

  return {
    /**
     * One‑shot analyze request.
     * Sends the raw T&C text to the backend.
     */
    async analyze(text: string, token: string): Promise<AnalysisResponsePayload> {
      return request<AnalysisResponsePayload>("POST", "/api/v1/reports/analyze", { text }, token);
    },

    /**
     * Retrieve a list of saved reports for the authenticated user.
     * Shape of response is inferred from the backend; caller can type as needed.
     */
    async listReports(token: string): Promise<any> {
      return request<any>("GET", "/api/v1/reports", null, token);
    },

    /**
     * Retrieve a specific report by ID.
     */
    async getReport(reportId: string, token: string): Promise<any> {
      return request<any>("GET", `/api/v1/reports/${reportId}`, null, token);
    },
  };
}
