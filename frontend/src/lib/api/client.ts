/* Architecture note:
 * The dashboard hook talks only to this client so endpoint paths and headers
 * stay centralized. This makes it straightforward to add auth tokens later
 * without touching component code.
 */

import type {
  AgreementCreateRequest,
  AgreementResponse,
  AnalysisTriggerRequest,
  ReportAnalyzeRequest,
  ReportListItemResponse,
  ReportResponse,
} from './contracts';

export interface DashboardApiClientConfig {
  baseUrl: string;
  getSessionId: () => string;
  // Optional auth seam: supply bearer token resolver when login is introduced.
  getAccessToken?: () => string | null;
  fetchImpl?: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
}

export class DashboardApiError extends Error {
  readonly status: number;
  readonly details: unknown;

  constructor(message: string, status: number, details: unknown) {
    super(message);
    this.name = 'DashboardApiError';
    this.status = status;
    this.details = details;
  }
}

/**
 * Typed API boundary for dashboard features.
 * Centralizing HTTP behavior here keeps components transport-agnostic.
 */
export class DashboardApiClient {
  private readonly baseUrl: string;
  private readonly getSessionId: () => string;
  private readonly getAccessToken?: () => string | null;
  private readonly fetchImpl: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

  constructor(config: DashboardApiClientConfig) {
    this.baseUrl = config.baseUrl.replace(/\/+$/, '');
    this.getSessionId = config.getSessionId;
    this.getAccessToken = config.getAccessToken;
    const fetchCandidate = config.fetchImpl ?? globalThis.fetch.bind(globalThis);
    this.fetchImpl = (input: RequestInfo | URL, init?: RequestInit) =>
      fetchCandidate(input, init);
  }

  async createAgreement(payload: AgreementCreateRequest): Promise<AgreementResponse> {
    return this.request<AgreementResponse>('/agreements', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async triggerAnalysis(
    agreementId: string,
    payload: AnalysisTriggerRequest,
  ): Promise<ReportResponse> {
    return this.request<ReportResponse>(`/agreements/${agreementId}/analyses`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async listReports(): Promise<ReportListItemResponse[]> {
    return this.request<ReportListItemResponse[]>('/reports');
  }

  async submitAndAnalyze(payload: ReportAnalyzeRequest): Promise<ReportResponse> {
    return this.request<ReportResponse>('/reports/analyze', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async getReport(reportId: string): Promise<ReportResponse> {
    return this.request<ReportResponse>(`/reports/${reportId}`);
  }

  private async request<T>(path: string, init?: RequestInit): Promise<T> {
    // Session scoping is used today; bearer auth can be layered in without UI changes.
    const accessToken = this.getAccessToken?.();
    const authorizationHeader =
      accessToken && accessToken.trim() ? { Authorization: `Bearer ${accessToken}` } : {};

    const response = await this.fetchImpl(`${this.baseUrl}${path}`, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        'X-Session-Id': this.getSessionId(),
        ...authorizationHeader,
        ...(init?.headers ?? {}),
      },
    });

    const contentType = response.headers.get('content-type') ?? '';
    const isJson = contentType.includes('application/json');
    const payload = isJson ? await response.json() : null;

    if (!response.ok) {
      const message =
        typeof payload === 'object' && payload && 'detail' in payload
          ? String(payload.detail)
          : `API request failed with status ${response.status}`;
      throw new DashboardApiError(message, response.status, payload);
    }

    return payload as T;
  }
}
