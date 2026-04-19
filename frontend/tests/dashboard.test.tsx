import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { DashboardPage } from '../src/features/dashboard/DashboardPage';
import { MAX_TERMS_TEXT_LENGTH } from '../src/lib/security/inputValidation';
import type {
  ReportListItemResponse,
  ReportResponse,
  TrackedPolicyCreateResponse,
  TrackedPolicyResponse,
} from '../src/lib/api/contracts';

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      'Content-Type': 'application/json',
    },
  });
}

function buildReport(overrides?: Partial<ReportResponse>): ReportResponse {
  return {
    id: '00000000-0000-4000-8000-000000000001',
    agreement_id: '10000000-0000-4000-8000-000000000001',
    source_type: 'url',
    source_value: 'https://example.com/terms',
    raw_input_excerpt: 'Sample excerpt for testing',
    status: 'completed',
    summary: 'Detected arbitration and auto-renewal concerns.',
    trust_score: 54,
    model_name: 'deterministic-keyword-v1',
    flagged_clauses: [
      {
        clause_type: 'forced_arbitration',
        severity: 'high',
        excerpt: 'Users agree to arbitration.',
        explanation: 'Limits legal options.',
      },
    ],
    created_at: '2026-03-14T10:00:00Z',
    completed_at: '2026-03-14T10:00:01Z',
    ...overrides,
  };
}

function buildListItem(overrides?: Partial<ReportListItemResponse>): ReportListItemResponse {
  return {
    id: '00000000-0000-4000-8000-000000000001',
    agreement_id: '10000000-0000-4000-8000-000000000001',
    source_type: 'url',
    source_value: 'https://example.com/terms',
    status: 'completed',
    trust_score: 54,
    model_name: 'deterministic-keyword-v1',
    created_at: '2026-03-14T10:00:00Z',
    ...overrides,
  };
}

function buildTrackedPolicy(overrides?: Partial<TrackedPolicyResponse>): TrackedPolicyResponse {
  return {
    id: '20000000-0000-4000-8000-000000000001',
    canonical_url: 'https://example.com/legal/terms',
    display_name: 'Example Terms',
    source_type: 'url',
    tracking_status: 'active',
    last_checked_at: '2026-03-24T15:30:00Z',
    created_at: '2026-03-24T15:30:00Z',
    snapshot_version_count: 1,
    ...overrides,
  };
}

function buildTrackedPolicyCreateResponse(
  overrides?: Partial<TrackedPolicyCreateResponse>,
): TrackedPolicyCreateResponse {
  return {
    ...buildTrackedPolicy(),
    baseline_report_id: '00000000-0000-4000-8000-000000000001',
    baseline_report_action: 'created',
    ...overrides,
  };
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  window.localStorage.clear();
});

describe('DashboardPage', () => {
  it('submits terms, shows analysis summary, and updates saved reports history', async () => {
    const report = buildReport();
    let listCalls = 0;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? 'GET';

      if (url.endsWith('/reports') && method === 'GET') {
        listCalls += 1;
        if (listCalls === 1) {
          return jsonResponse([]);
        }
        return jsonResponse([buildListItem()]);
      }
      if (url.endsWith('/tracked-policies') && method === 'GET') {
        return jsonResponse([]);
      }
      if (url.endsWith('/reports/analyze') && method === 'POST') {
        return jsonResponse(report, 201);
      }
      throw new Error(`Unexpected request: ${method} ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<DashboardPage />);

    await waitFor(() =>
      expect(screen.getByText('No reports yet. Submit a terms agreement to create one.')).toBeTruthy(),
    );

    const user = userEvent.setup();
    await user.type(screen.getByLabelText('Source URL'), 'https://example.com/terms');
    await user.type(
      screen.getByLabelText('Terms text'),
      'These terms include arbitration and renews automatically.',
    );
    await user.click(screen.getByRole('button', { name: 'Analyze and save report' }));

    await waitFor(() => expect(screen.getByText('Analysis complete. Report has been saved.')).toBeTruthy());
    expect(screen.getByText('Trust score: 54 / 100')).toBeTruthy();
    expect(screen.getByText('Detected arbitration and auto-renewal concerns.')).toBeTruthy();
    expect(screen.getAllByText(/https:\/\/example.com\/terms/).length).toBeGreaterThan(0);
    expect(screen.getByText(/forced arbitration/)).toBeTruthy();
  });

  it('shows loading and empty states while report history is fetched', async () => {
    let resolveRequest: ((response: Response) => void) | null = null;
    const pending = new Promise<Response>((resolve) => {
      resolveRequest = resolve;
    });

    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? 'GET';
      if (url.endsWith('/reports') && method === 'GET') {
        return pending;
      }
      if (url.endsWith('/tracked-policies') && method === 'GET') {
        return jsonResponse([]);
      }
      throw new Error(`Unexpected request: ${method} ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<DashboardPage />);
    expect(screen.getByText('Loading report history...')).toBeTruthy();

    resolveRequest?.(jsonResponse([]));

    await waitFor(() =>
      expect(screen.getByText('No reports yet. Submit a terms agreement to create one.')).toBeTruthy(),
    );
  });

  it('shows a user-visible error state when the API request fails', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? 'GET';

      if (url.endsWith('/reports') && method === 'GET') {
        throw new Error('Network error while loading reports');
      }
      if (url.endsWith('/tracked-policies') && method === 'GET') {
        return jsonResponse([]);
      }
      throw new Error(`Unexpected request: ${method} ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<DashboardPage />);

    await waitFor(() =>
      expect(screen.getByText('Network error while loading reports')).toBeTruthy(),
    );
  });

  it('blocks unsafe source URLs before they are sent to the API', async () => {
    const fetchMock = vi.fn(async () => jsonResponse([]));
    vi.stubGlobal('fetch', fetchMock);

    render(<DashboardPage />);

    await waitFor(() =>
      expect(screen.getByText('No reports yet. Submit a terms agreement to create one.')).toBeTruthy(),
    );

    const user = userEvent.setup();
    await user.type(screen.getByLabelText('Source URL'), 'http://localhost/private-terms');
    await user.type(
      screen.getByLabelText('Terms text'),
      'These terms include arbitration and automatic renewal clauses.',
    );
    await user.click(screen.getByRole('button', { name: 'Analyze and save report' }));

    await waitFor(() =>
      expect(screen.getByText('Source URL must target a public hostname.')).toBeTruthy(),
    );
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('shows the terms character counter and blocks submission once the UI cap is exceeded', async () => {
    const fetchMock = vi.fn(async () => jsonResponse([]));
    vi.stubGlobal('fetch', fetchMock);

    render(<DashboardPage />);

    await waitFor(() =>
      expect(screen.getByText('No reports yet. Submit a terms agreement to create one.')).toBeTruthy(),
    );

    const termsField = screen.getByLabelText('Terms text');
    fireEvent.change(termsField, { target: { value: 'x'.repeat(MAX_TERMS_TEXT_LENGTH + 25) } });

    expect(screen.getByText('200,025 / 200,000 characters')).toBeTruthy();
    expect(
      screen.getByText("You've exceeded the 200,000 character limit by 25 characters."),
    ).toBeTruthy();
    expect(
      screen.getByTitle("You've exceeded the 200,000 character limit by 25 characters."),
    ).toBeTruthy();
    expect((screen.getByRole('button', { name: 'Analyze and save report' }) as HTMLButtonElement).disabled).toBe(
      true,
    );
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('renders saved report history and allows selecting a prior report', async () => {
    const reportOne = buildReport({
      id: '00000000-0000-4000-8000-000000000001',
      summary: 'First summary',
      trust_score: 72,
      source_value: 'https://service-one.example/terms',
      flagged_clauses: [],
    });
    const reportTwo = buildReport({
      id: '00000000-0000-4000-8000-000000000002',
      summary: 'Second summary with risk',
      trust_score: 41,
      source_value: 'https://service-two.example/terms',
      flagged_clauses: [
        {
          clause_type: 'auto_renewal',
          severity: 'high',
          excerpt: 'Renews automatically every month',
          explanation: 'Potential unexpected recurring charges.',
        },
      ],
    });

    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? 'GET';

      if (url.endsWith('/reports') && method === 'GET') {
        return jsonResponse([
          buildListItem({
            id: '00000000-0000-4000-8000-000000000001',
            source_value: reportOne.source_value,
            trust_score: reportOne.trust_score,
          }),
          buildListItem({
            id: '00000000-0000-4000-8000-000000000002',
            source_value: reportTwo.source_value,
            trust_score: reportTwo.trust_score,
          }),
        ]);
      }
      if (url.endsWith('/tracked-policies') && method === 'GET') {
        return jsonResponse([]);
      }
      if (url.endsWith('/reports/00000000-0000-4000-8000-000000000002') && method === 'GET') {
        return jsonResponse(reportTwo);
      }
      if (url.endsWith('/reports/00000000-0000-4000-8000-000000000001') && method === 'GET') {
        return jsonResponse(reportOne);
      }
      throw new Error(`Unexpected request: ${method} ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<DashboardPage />);

    await waitFor(() =>
      expect(screen.getByText('https://service-one.example/terms')).toBeTruthy(),
    );
    expect(screen.getByText('https://service-two.example/terms')).toBeTruthy();

    const user = userEvent.setup();
    await user.click(
      screen.getByRole('button', { name: /URL https:\/\/service-two\.example\/terms/i }),
    );

    await waitFor(() => expect(screen.getByText('Trust score: 41 / 100')).toBeTruthy());
    expect(screen.getByText('Second summary with risk')).toBeTruthy();
    expect(screen.getByText(/auto renewal/)).toBeTruthy();
  });

  it('loads the watchlist and lets the user add a tracked policy', async () => {
    const baselineReport = buildReport({
      source_value: 'https://example.com/legal/terms',
      raw_input_excerpt: 'These terms include arbitration and automatic renewal clauses.',
    });
    const createdTrackedPolicy = buildTrackedPolicy();
    const createdTrackedPolicyResponse = buildTrackedPolicyCreateResponse({
      ...createdTrackedPolicy,
      baseline_report_id: baselineReport.id,
      baseline_report_action: 'created',
    });
    const baselineReportListItem = buildListItem({
      id: baselineReport.id,
      source_value: baselineReport.source_value,
      trust_score: baselineReport.trust_score,
    });
    let reportListCalls = 0;
    let trackedPolicyListCalls = 0;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? 'GET';

      if (url.endsWith('/reports') && method === 'GET') {
        reportListCalls += 1;
        if (reportListCalls === 1) {
          return jsonResponse([]);
        }
        return jsonResponse([baselineReportListItem]);
      }
      if (url.endsWith(`/reports/${baselineReport.id}`) && method === 'GET') {
        return jsonResponse(baselineReport);
      }
      if (url.endsWith('/tracked-policies') && method === 'GET') {
        trackedPolicyListCalls += 1;
        if (trackedPolicyListCalls === 1) {
          return jsonResponse([]);
        }
        return jsonResponse([createdTrackedPolicy]);
      }
      if (url.endsWith('/tracked-policies') && method === 'POST') {
        return jsonResponse(createdTrackedPolicyResponse, 201);
      }
      throw new Error(`Unexpected request: ${method} ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<DashboardPage />);

    await waitFor(() =>
      expect(
        screen.getByText('No tracked policies yet. Add a policy URL to start monitoring changes.'),
      ).toBeTruthy(),
    );

    const user = userEvent.setup();
    await user.type(screen.getByLabelText('Policy URL'), 'https://example.com/legal/terms');
    await user.click(screen.getByRole('button', { name: 'Add to watchlist' }));

    await waitFor(() =>
      expect(
        screen.getByText(
          'Example Terms was analyzed, saved as a baseline report, and added to your watchlist with its first stored version.',
        ),
      ).toBeTruthy(),
    );
    expect(screen.getByText('Example Terms')).toBeTruthy();
    expect(screen.getAllByText('https://example.com/legal/terms').length).toBeGreaterThan(0);
    expect(screen.getByText(/active/i)).toBeTruthy();
    expect(screen.getByText(/1 stored version - last checked/i)).toBeTruthy();
    expect(
      screen.getByText(
        'New watchlist entries begin at 1 stored version because enrollment saves the verified baseline as the first tracked capture.',
      ),
    ).toBeTruthy();
    expect(screen.getByText('Trust score: 54 / 100')).toBeTruthy();
    expect(screen.getByText('Detected arbitration and auto-renewal concerns.')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Check now' })).toBeTruthy();
  });

  it('reuses an existing baseline report when adding a tracked policy to the watchlist', async () => {
    const existingBaselineReport = buildReport({
      id: '00000000-0000-4000-8000-000000000004',
      agreement_id: '10000000-0000-4000-8000-000000000004',
      source_value: 'https://example.com/legal/terms',
      summary: 'Existing baseline summary',
      trust_score: 61,
    });
    const existingBaselineListItem = buildListItem({
      id: existingBaselineReport.id,
      agreement_id: existingBaselineReport.agreement_id,
      source_value: existingBaselineReport.source_value,
      trust_score: existingBaselineReport.trust_score,
    });
    const createdTrackedPolicy = buildTrackedPolicy({
      id: '20000000-0000-4000-8000-000000000004',
      canonical_url: 'https://example.com/legal/terms',
      display_name: 'Example Terms',
    });
    const createResponse = buildTrackedPolicyCreateResponse({
      ...createdTrackedPolicy,
      baseline_report_id: existingBaselineReport.id,
      baseline_report_action: 'reused',
    });
    let trackedPolicyListCalls = 0;
    let reportListCalls = 0;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? 'GET';

      if (url.endsWith('/reports') && method === 'GET') {
        reportListCalls += 1;
        return jsonResponse([existingBaselineListItem]);
      }
      if (url.endsWith(`/reports/${existingBaselineReport.id}`) && method === 'GET') {
        return jsonResponse(existingBaselineReport);
      }
      if (url.endsWith('/tracked-policies') && method === 'GET') {
        trackedPolicyListCalls += 1;
        if (trackedPolicyListCalls === 1) {
          return jsonResponse([]);
        }
        return jsonResponse([createdTrackedPolicy]);
      }
      if (url.endsWith('/tracked-policies') && method === 'POST') {
        return jsonResponse(createResponse, 201);
      }
      throw new Error(`Unexpected request: ${method} ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<DashboardPage />);

    await waitFor(() =>
      expect(
        screen.getByText('No tracked policies yet. Add a policy URL to start monitoring changes.'),
      ).toBeTruthy(),
    );

    const user = userEvent.setup();
    await user.type(screen.getByLabelText('Policy URL'), 'https://example.com/legal/terms');
    await user.click(screen.getByRole('button', { name: 'Add to watchlist' }));

    await waitFor(() =>
      expect(
        screen.getByText(
          'Example Terms reused an existing saved baseline report and was added to your watchlist with its first stored version.',
        ),
      ).toBeTruthy(),
    );
    expect(screen.getByText('Existing baseline summary')).toBeTruthy();
    expect(reportListCalls).toBe(2);
  });

  it('shows an error when adding an invalid tracked-policy URL', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? 'GET';

      if (url.endsWith('/reports') && method === 'GET') {
        return jsonResponse([]);
      }
      if (url.endsWith('/tracked-policies') && method === 'GET') {
        return jsonResponse([]);
      }
      throw new Error(`Unexpected request: ${method} ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<DashboardPage />);

    await waitFor(() =>
      expect(
        screen.getByText('No tracked policies yet. Add a policy URL to start monitoring changes.'),
      ).toBeTruthy(),
    );

    const user = userEvent.setup();
    await user.type(screen.getByLabelText('Policy URL'), 'http://localhost/private-terms');
    await user.click(screen.getByRole('button', { name: 'Add to watchlist' }));

    await waitFor(() =>
      expect(screen.getByText('Source URL must target a public hostname.')).toBeTruthy(),
    );
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('shows an actionable backend error when the policy URL returns a missing page', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? 'GET';

      if (url.endsWith('/reports') && method === 'GET') {
        return jsonResponse([]);
      }
      if (url.endsWith('/tracked-policies') && method === 'GET') {
        return jsonResponse([]);
      }
      if (url.endsWith('/tracked-policies') && method === 'POST') {
        return jsonResponse(
          {
            detail:
              "That policy page returned 404 Not Found. Check that the link is current or use the service's public legal page.",
          },
          422,
        );
      }
      throw new Error(`Unexpected request: ${method} ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<DashboardPage />);

    await waitFor(() =>
      expect(
        screen.getByText('No tracked policies yet. Add a policy URL to start monitoring changes.'),
      ).toBeTruthy(),
    );

    const user = userEvent.setup();
    await user.type(screen.getByLabelText('Policy URL'), 'https://example.com/missing-terms');
    await user.click(screen.getByRole('button', { name: 'Add to watchlist' }));

    await waitFor(() =>
      expect(
        screen.getByText(
          "That policy page returned 404 Not Found. Check that the link is current or use the service's public legal page.",
        ),
      ).toBeTruthy(),
    );
  });

  it('surfaces actionable check failures and refreshes the row to invalid source', async () => {
    const initialTrackedPolicy = buildTrackedPolicy({
      id: '20000000-0000-4000-8000-000000000003',
      canonical_url: 'https://example.com/legal/terms',
      display_name: 'Example Terms',
      tracking_status: 'active',
      snapshot_version_count: 1,
    });
    const failedTrackedPolicy = buildTrackedPolicy({
      id: '20000000-0000-4000-8000-000000000003',
      canonical_url: 'https://example.com/legal/terms',
      display_name: 'Example Terms',
      tracking_status: 'invalid_source',
      snapshot_version_count: 1,
    });
    let reportListCalls = 0;
    let trackedPolicyListCalls = 0;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? 'GET';

      if (url.endsWith('/reports') && method === 'GET') {
        reportListCalls += 1;
        return jsonResponse([]);
      }
      if (url.endsWith('/tracked-policies') && method === 'GET') {
        trackedPolicyListCalls += 1;
        if (trackedPolicyListCalls === 1) {
          return jsonResponse([initialTrackedPolicy]);
        }
        return jsonResponse([failedTrackedPolicy]);
      }
      if (
        url.endsWith('/tracked-policies/20000000-0000-4000-8000-000000000003/check') &&
        method === 'POST'
      ) {
        return jsonResponse(
          {
            detail:
              'That policy page is blocking access. Use a public terms or privacy page that does not require sign-in.',
          },
          422,
        );
      }
      throw new Error(`Unexpected request: ${method} ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<DashboardPage />);

    await waitFor(() => expect(screen.getByText('Example Terms')).toBeTruthy());

    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Check now' }));

    await waitFor(() =>
      expect(
        screen.getByText(
          'That policy page is blocking access. Use a public terms or privacy page that does not require sign-in.',
        ),
      ).toBeTruthy(),
    );
    expect(screen.getByText(/invalid source/i)).toBeTruthy();
    expect(
      screen.getByText(
        "The latest check could not read this page. Use the service's public terms, privacy, or legal page if the link changed.",
      ),
    ).toBeTruthy();
    expect(reportListCalls).toBe(1);
  });

  it('lets the user remove a tracked policy from the watchlist', async () => {
    const trackedPolicy = buildTrackedPolicy({
      id: '20000000-0000-4000-8000-000000000002',
      canonical_url: 'https://service-two.example/legal/terms',
      display_name: 'Service Two Legal Terms',
      tracking_status: 'active',
    });
    let trackedPolicyListCalls = 0;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? 'GET';

      if (url.endsWith('/reports') && method === 'GET') {
        return jsonResponse([]);
      }
      if (url.endsWith('/tracked-policies') && method === 'GET') {
        trackedPolicyListCalls += 1;
        if (trackedPolicyListCalls === 1) {
          return jsonResponse([trackedPolicy]);
        }
        return jsonResponse([]);
      }
      if (
        url.endsWith('/tracked-policies/20000000-0000-4000-8000-000000000002') &&
        method === 'DELETE'
      ) {
        return new Response(null, { status: 204 });
      }
      throw new Error(`Unexpected request: ${method} ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<DashboardPage />);

    await waitFor(() =>
      expect(screen.getByText('Service Two Legal Terms')).toBeTruthy(),
    );

    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Remove' }));

    await waitFor(() =>
      expect(screen.getByText('Policy removed from your watchlist.')).toBeTruthy(),
    );
    expect(
      screen.getByText('No tracked policies yet. Add a policy URL to start monitoring changes.'),
    ).toBeTruthy();
  });
});
