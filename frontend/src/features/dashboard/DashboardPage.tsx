/* Architecture note:
 * Layer: feature container.
 * This component wires the dashboard hook, API client, and presentational
 * components. Business/data orchestration stays in the hook and API client.
 * Auth/token sourcing should stay outside this module.
 */

import { type ReactNode, useEffect, useMemo } from 'react';

import type { DashboardApiClient } from '../../lib/api/client';
import { createDashboardApiClient } from '../../lib/api/createDashboardApiClient';
import { AgreementSubmissionForm } from './components/AgreementSubmissionForm';
import { AnalysisSummaryCard } from './components/AnalysisSummaryCard';
import { FlaggedClausesList } from './components/FlaggedClausesList';
import { ReportHistoryList } from './components/ReportHistoryList';
import { useDashboardReports } from './hooks/useDashboardReports';

interface DashboardPageProps {
  // Optional injection seam for tests and auth-aware wrappers.
  apiClient?: DashboardApiClient;
  // Context label/action are generic to avoid auth coupling in dashboard code.
  contextLabel?: string | null;
  headerAction?: ReactNode;
}

export function DashboardPage({
  apiClient,
  contextLabel,
  headerAction,
}: DashboardPageProps) {
  const fallbackApiClient = useMemo(() => createDashboardApiClient(), []);
  const effectiveApiClient = apiClient ?? fallbackApiClient;

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
  } = useDashboardReports(effectiveApiClient);

  useEffect(() => {
    void loadReportHistory();
  }, [loadReportHistory]);

  return (
    <main className="dashboard">
      <header className="dashboard-topbar">
        <div className="dashboard-header-copy">
          <h1>Terms and Conditions Dashboard</h1>
          <p className="dashboard-subtitle">
            Submit terms, generate analysis, and review saved reports.
          </p>
          {contextLabel ? <p className="dashboard-user">{contextLabel}</p> : null}
        </div>
        {headerAction ? <div className="header-actions">{headerAction}</div> : null}
      </header>

      {errorMessage || successMessage ? (
        <section className="dashboard-feedback" aria-live="polite">
          {errorMessage ? (
            <div className="error-banner" role="alert">
              <span>{errorMessage}</span>
              <button type="button" className="button-link" onClick={clearMessages}>
                Dismiss
              </button>
            </div>
          ) : null}

          {successMessage ? (
            <div className="success-banner" role="status">
              <span>{successMessage}</span>
              <button type="button" className="button-link" onClick={clearMessages}>
                Dismiss
              </button>
            </div>
          ) : null}
        </section>
      ) : null}

      <section className="dashboard-layout">
        {/* Left column handles submission + retrieval controls; right column is read-only analysis output. */}
        <div className="dashboard-column dashboard-column-primary">
          <AgreementSubmissionForm onSubmit={submitAndAnalyze} isSubmitting={isSubmitting} />
          <ReportHistoryList
            reports={reportHistory}
            selectedReportId={selectedReport?.id ?? null}
            isLoadingHistory={isLoadingHistory}
            onSelectReport={selectReport}
          />
        </div>
        <div className="dashboard-column dashboard-column-analysis">
          <AnalysisSummaryCard report={selectedReport} isLoadingReport={isLoadingReport} />
          <FlaggedClausesList report={selectedReport} />
        </div>
      </section>
    </main>
  );
}
