import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { DashboardPage } from '../src/features/dashboard/DashboardPage';
import { MAX_TERMS_TEXT_LENGTH } from '../src/lib/security/inputValidation';
import type {
  ReportListItemResponse,
  ReportResponse,
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
    const fetchMock = vi.fn(async () => {
      throw new Error('Network error while loading reports');
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
    expect(fetchMock).toHaveBeenCalledTimes(1);
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
    expect(fetchMock).toHaveBeenCalledTimes(1);
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
});
