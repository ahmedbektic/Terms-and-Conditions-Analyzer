/* Architecture note:
 * Layer: feature container.
 * This component wires the dashboard hook, API client, and presentational
 * components. Business/data orchestration stays in the hook and API client.
 */

import { useEffect, useMemo } from 'react';

import { DashboardApiClient } from '../../lib/api/client';
import { getOrCreateSessionId } from '../../lib/session/sessionId';
import { AgreementSubmissionForm } from './components/AgreementSubmissionForm';
import { AnalysisSummaryCard } from './components/AnalysisSummaryCard';
import { FlaggedClausesList } from './components/FlaggedClausesList';
import { ReportHistoryList } from './components/ReportHistoryList';
import { useDashboardReports } from './hooks/useDashboardReports';

function resolveApiBaseUrl(): string {
  const configured = import.meta.env.VITE_API_BASE_URL;
  return configured ? String(configured) : 'http://localhost:8000/api/v1';
}

export function DashboardPage() {
  const apiClient = useMemo(
    () =>
      new DashboardApiClient({
        baseUrl: resolveApiBaseUrl(),
        // Session id is today's owner key until auth-backed user identities are added.
        getSessionId: getOrCreateSessionId,
      }),
    [],
  );

  const {
    selectedReport,
    reportHistory,
    isSubmitting,
    isLoadingHistory,
    isLoadingReport,
    errorMessage,
    successMessage,
    submitAndAnalyze,
    loadReportHistory,
    selectReport,
    clearMessages,
  } = useDashboardReports(apiClient);

  useEffect(() => {
    void loadReportHistory();
  }, [loadReportHistory]);

  return (
    <main className="dashboard">
      <header className="dashboard-header">
        <h1>Terms and Conditions Dashboard</h1>
        <p>Submit terms, generate analysis, and review saved reports.</p>
      </header>

      {errorMessage ? (
        <div className="error-banner" role="alert">
          <span>{errorMessage}</span>
          <button type="button" onClick={clearMessages}>
            Dismiss
          </button>
        </div>
      ) : null}

      {successMessage ? (
        <div className="success-banner" role="status">
          <span>{successMessage}</span>
          <button type="button" onClick={clearMessages}>
            Dismiss
          </button>
        </div>
      ) : null}

      <AgreementSubmissionForm onSubmit={submitAndAnalyze} isSubmitting={isSubmitting} />

      <section className="grid">
        <AnalysisSummaryCard report={selectedReport} isLoadingReport={isLoadingReport} />
        <FlaggedClausesList report={selectedReport} />
      </section>

      <ReportHistoryList
        reports={reportHistory}
        selectedReportId={selectedReport?.id ?? null}
        isLoadingHistory={isLoadingHistory}
        onSelectReport={selectReport}
      />
    </main>
  );
}
