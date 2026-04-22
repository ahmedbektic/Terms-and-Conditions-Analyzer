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
  TrackedPolicyCreateResponse,
  TrackedPolicyCreateRequest,
  TrackedPolicySnapshotComparisonResponse,
  TrackedPolicySnapshotResponse,
  TrackedPolicyResponse,
  TrackedPolicyCheckExecutionEnvelope,
  TrackedPolicyCheckExecutionResponse,
} from './contracts';
import {
  sanitizeAgreementCreateInput,
  sanitizeReportAnalyzeInput,
  sanitizeTrackedPolicyCreateInput,
  validateUuid,
} from '../security/inputValidation';

export interface DashboardApiClientConfig {
  baseUrl: string;
  // Auth seam: caller provides access token resolver.
  // extension can reuse this by providing its own token source.
  getAccessToken?: () => string | null;
  fetchImpl?: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
}

const REQUEST_TIMEOUT_MS = 15000;
const LONG_RUNNING_REQUEST_TIMEOUT_MS = 90000;

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

  async createTrackedPolicy(
    payload: TrackedPolicyCreateRequest,
  ): Promise<TrackedPolicyCreateResponse> {
    const sanitizedPayload = sanitizeTrackedPolicyCreateInput(payload);
    return this.request<TrackedPolicyCreateResponse>('/tracked-policies', {
      method: 'POST',
      body: JSON.stringify(sanitizedPayload),
    }, { timeoutMs: LONG_RUNNING_REQUEST_TIMEOUT_MS });
  }

  async listTrackedPolicies(): Promise<TrackedPolicyResponse[]> {
    return this.request<TrackedPolicyResponse[]>('/tracked-policies');
  }

  async checkTrackedPolicy(trackedPolicyId: string): Promise<TrackedPolicyCheckExecutionEnvelope> {
    return this.request<TrackedPolicyCheckExecutionEnvelope>(
      `/tracked-policies/${validateUuid(trackedPolicyId, 'Tracked policy id')}/check`,
      {
        method: 'POST',
      },
      { timeoutMs: LONG_RUNNING_REQUEST_TIMEOUT_MS }
    );
  }

  async getTrackedPolicyExecution(executionId: string): Promise<TrackedPolicyCheckExecutionResponse> {
    return this.request<TrackedPolicyCheckExecutionResponse>(
      `/tracked-policies/executions/${validateUuid(executionId, 'Execution id')}`
    );
  }

  async removeTrackedPolicy(trackedPolicyId: string): Promise<void> {
    await this.request<void>(
      `/tracked-policies/${validateUuid(trackedPolicyId, 'Tracked policy id')}`,
      {
        method: 'DELETE',
      },
    );
  }

  async listTrackedPolicySnapshots(trackedPolicyId: string): Promise<TrackedPolicySnapshotResponse[]> {
    return this.request<TrackedPolicySnapshotResponse[]>(
      `/tracked-policies/${validateUuid(trackedPolicyId, 'Tracked policy id')}/snapshots`,
    );
  }

  async compareTrackedPolicySnapshots(
    trackedPolicyId: string,
    snapshotAId: string,
    snapshotBId: string,
  ): Promise<TrackedPolicySnapshotComparisonResponse> {
    const trackedPolicy = validateUuid(trackedPolicyId, 'Tracked policy id');
    const snapshotA = validateUuid(snapshotAId, 'Snapshot A id');
    const snapshotB = validateUuid(snapshotBId, 'Snapshot B id');
    return this.request<TrackedPolicySnapshotComparisonResponse>(
      `/tracked-policies/${trackedPolicy}/compare?snapshot_a=${snapshotA}&snapshot_b=${snapshotB}`,
    );
  }

  async submitAndAnalyze(payload: ReportAnalyzeRequest): Promise<ReportResponse> {
    const sanitizedPayload = sanitizeReportAnalyzeInput(payload);
    return this.request<ReportResponse>('/reports/analyze', {
      method: 'POST',
      body: JSON.stringify(sanitizedPayload),
    }, { timeoutMs: LONG_RUNNING_REQUEST_TIMEOUT_MS });
  }

  async getReport(reportId: string): Promise<ReportResponse> {
    return this.request<ReportResponse>(`/reports/${validateUuid(reportId, 'Report id')}`);
  }

  private async request<T>(
    path: string,
    init?: RequestInit,
    options?: { timeoutMs?: number },
  ): Promise<T> {
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

    const timeoutController = new AbortController();
    const timeoutHandle = globalThis.setTimeout(() => {
      timeoutController.abort();
    }, options?.timeoutMs ?? REQUEST_TIMEOUT_MS);

    if (init?.signal) {
      if (init.signal.aborted) {
        timeoutController.abort();
      } else {
        init.signal.addEventListener('abort', () => timeoutController.abort(), { once: true });
      }
    }

    let response: Response;
    try {
      response = await this.fetchImpl(`${this.baseUrl}${path}`, {
        ...init,
        headers,
        signal: timeoutController.signal,
      });
    } catch (error) {
      if (timeoutController.signal.aborted && !init?.signal?.aborted) {
        throw new DashboardApiError(
          'API request timed out. Check that the backend is reachable and try again.',
          504,
          null,
        );
      }
      throw error;
    } finally {
      globalThis.clearTimeout(timeoutHandle);
    }

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
