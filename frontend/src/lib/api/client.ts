/* Architecture note:
 * The dashboard hook talks only to this client so endpoint paths and headers
 * stay centralized. Bearer-token propagation happens here so feature components
 * stay transport-agnostic.
 */

import type {
  AgreementCreateRequest,
  AgreementResponse,
  AnalysisTriggerRequest,
  ReportAnalyzeRequest,
  ReportListItemResponse,
  ReportResponse,
} from './contracts';
import {
  sanitizeAgreementCreateInput,
  sanitizeReportAnalyzeInput,
  validateUuid,
} from '../security/inputValidation';

export interface DashboardApiClientConfig {
  baseUrl: string;
  // Auth seam: caller provides access token resolver.
  // extension can reuse this by providing its own token source.
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
  private readonly getAccessToken?: () => string | null;
  private readonly fetchImpl: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

  constructor(config: DashboardApiClientConfig) {
    this.baseUrl = config.baseUrl.replace(/\/+$/, '');
    this.getAccessToken = config.getAccessToken;
    const fetchCandidate = config.fetchImpl ?? globalThis.fetch.bind(globalThis);
    this.fetchImpl = (input: RequestInfo | URL, init?: RequestInit) =>
      fetchCandidate(input, init);
  }

  async createAgreement(payload: AgreementCreateRequest): Promise<AgreementResponse> {
    const sanitizedPayload = sanitizeAgreementCreateInput(payload);
    return this.request<AgreementResponse>('/agreements', {
      method: 'POST',
      body: JSON.stringify(sanitizedPayload),
    });
  }

  async triggerAnalysis(
    agreementId: string,
    payload: AnalysisTriggerRequest,
  ): Promise<ReportResponse> {
    const normalizedAgreementId = validateUuid(agreementId, 'Agreement id');
    return this.request<ReportResponse>(`/agreements/${normalizedAgreementId}/analyses`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async listReports(): Promise<ReportListItemResponse[]> {
    return this.request<ReportListItemResponse[]>('/reports');
  }

  async submitAndAnalyze(payload: ReportAnalyzeRequest): Promise<ReportResponse> {
    const sanitizedPayload = sanitizeReportAnalyzeInput(payload);
    return this.request<ReportResponse>('/reports/analyze', {
      method: 'POST',
      body: JSON.stringify(sanitizedPayload),
    });
  }

  async getReport(reportId: string): Promise<ReportResponse> {
    return this.request<ReportResponse>(`/reports/${validateUuid(reportId, 'Report id')}`);
  }

  private async request<T>(path: string, init?: RequestInit): Promise<T> {
    const accessToken = this.getAccessToken?.();
    const headers = new Headers({
      'Content-Type': 'application/json',
    });

    if (accessToken && accessToken.trim()) {
      headers.set('Authorization', `Bearer ${accessToken}`);
    }

    // Caller-provided headers are applied last for deliberate overrides.
    if (init?.headers) {
      const callerHeaders = new Headers(init.headers);
      callerHeaders.forEach((value, key) => {
        headers.set(key, value);
      });
    }

    const response = await this.fetchImpl(`${this.baseUrl}${path}`, {
      ...init,
      headers,
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
