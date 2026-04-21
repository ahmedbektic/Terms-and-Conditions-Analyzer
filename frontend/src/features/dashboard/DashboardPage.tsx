/* Architecture note:
 * Layer: feature container.
 * This component wires the dashboard hook, API client, and presentational
 * components. Business/data orchestration stays in the hook and API client.
 * Auth/token sourcing should stay outside this module.
 */

import { type ReactNode, useCallback, useEffect, useMemo } from 'react';

import type { DashboardApiClient } from '../../lib/api/client';
import { createDashboardApiClient } from '../../lib/api/createDashboardApiClient';
import { AgreementSubmissionForm } from './components/AgreementSubmissionForm';
import { AnalysisSummaryCard } from './components/AnalysisSummaryCard';
import { FlaggedClausesList } from './components/FlaggedClausesList';
import { ReportHistoryList } from './components/ReportHistoryList';
import { TrackedPolicyComparePanel } from './components/TrackedPolicyComparePanel';
import { TrackedPolicyHistoryPanel } from './components/TrackedPolicyHistoryPanel';
import { TrackedPolicyWatchlistPanel } from './components/TrackedPolicyWatchlistPanel';
import { useDashboardReports } from './hooks/useDashboardReports';
import { useTrackedPolicies } from './hooks/useTrackedPolicies';

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
    errorMessage: reportErrorMessage,
    successMessage: reportSuccessMessage,
    submitAndAnalyze,
    loadReportHistory,
    selectReport,
    clearMessages: clearReportMessages,
  } = useDashboardReports(effectiveApiClient);
  const {
    trackedPolicies,
    isLoadingTrackedPolicies,
    isCreatingTrackedPolicy,
    checkingTrackedPolicyId,
    removingTrackedPolicyId,
    selectedTrackedPolicy,
    trackedPolicySnapshots,
    selectedSnapshotIds,
    trackedPolicyComparison,
    isLoadingTrackedPolicySnapshots,
    isLoadingTrackedPolicyComparison,
    errorMessage: trackedPolicyErrorMessage,
    successMessage: trackedPolicySuccessMessage,
    loadTrackedPolicies,
    createTrackedPolicy,
    checkTrackedPolicy,
    removeTrackedPolicy,
    openTrackedPolicyHistory,
    closeTrackedPolicyHistory,
    toggleTrackedPolicySnapshotSelection,
    compareSelectedTrackedPolicySnapshots,
    returnToTrackedPolicyHistory,
    clearMessages: clearTrackedPolicyMessages,
  } = useTrackedPolicies(effectiveApiClient);

  const loadDashboardData = useCallback(async () => {
    await Promise.allSettled([loadReportHistory(), loadTrackedPolicies()]);
  }, [loadReportHistory, loadTrackedPolicies]);

  useEffect(() => {
    void loadDashboardData();
  }, [loadDashboardData]);

  const handleCreateTrackedPolicy = useCallback(
    async (sourceUrl: string) => {
      const enrollmentResult = await createTrackedPolicy(sourceUrl);
      if (!enrollmentResult) {
        return;
      }

      await loadReportHistory();
      await selectReport(enrollmentResult.baselineReportId);
    },
    [createTrackedPolicy, loadReportHistory, selectReport],
  );

  const handleCheckTrackedPolicy = useCallback(
    async (trackedPolicyId: string) => {
      await checkTrackedPolicy(trackedPolicyId);
      await loadReportHistory();
    },
    [checkTrackedPolicy, loadReportHistory],
  );

  return (
    <main className="dashboard">
      <header className="dashboard-topbar">
        <div className="dashboard-header-copy">
          <h1>Terms and Conditions Dashboard</h1>
          <p className="dashboard-subtitle">
            Submit terms, review saved reports, and keep a watchlist of policies you want tracked.
          </p>
          {contextLabel ? <p className="dashboard-user">{contextLabel}</p> : null}
        </div>
        {headerAction ? <div className="header-actions">{headerAction}</div> : null}
      </header>

      {reportErrorMessage ||
      reportSuccessMessage ||
      trackedPolicyErrorMessage ||
      trackedPolicySuccessMessage ? (
        <section className="dashboard-feedback" aria-live="polite">
          {reportErrorMessage ? (
            <div className="error-banner" role="alert">
              <span>{reportErrorMessage}</span>
              <button type="button" className="button-link" onClick={clearReportMessages}>
                Dismiss
              </button>
            </div>
          ) : null}

          {reportSuccessMessage ? (
            <div className="success-banner" role="status">
              <span>{reportSuccessMessage}</span>
              <button type="button" className="button-link" onClick={clearReportMessages}>
                Dismiss
              </button>
            </div>
          ) : null}

          {trackedPolicyErrorMessage ? (
            <div className="error-banner" role="alert">
              <span>{trackedPolicyErrorMessage}</span>
              <button
                type="button"
                className="button-link"
                onClick={clearTrackedPolicyMessages}
              >
                Dismiss
              </button>
            </div>
          ) : null}

          {trackedPolicySuccessMessage ? (
            <div className="success-banner" role="status">
              <span>{trackedPolicySuccessMessage}</span>
              <button
                type="button"
                className="button-link"
                onClick={clearTrackedPolicyMessages}
              >
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
          <TrackedPolicyWatchlistPanel
            trackedPolicies={trackedPolicies}
            isLoadingTrackedPolicies={isLoadingTrackedPolicies}
            isCreatingTrackedPolicy={isCreatingTrackedPolicy}
            checkingTrackedPolicyId={checkingTrackedPolicyId}
            removingTrackedPolicyId={removingTrackedPolicyId}
            onCreateTrackedPolicy={handleCreateTrackedPolicy}
            onCheckTrackedPolicy={handleCheckTrackedPolicy}
            onRemoveTrackedPolicy={removeTrackedPolicy}
            onViewHistory={openTrackedPolicyHistory}
          />
          <ReportHistoryList
            reports={reportHistory}
            selectedReportId={selectedReport?.id ?? null}
            isLoadingHistory={isLoadingHistory}
            onSelectReport={selectReport}
          />
        </div>
        <div className="dashboard-column dashboard-column-analysis">
          {trackedPolicyComparison ? (
            <TrackedPolicyComparePanel
              comparison={trackedPolicyComparison}
              isLoading={isLoadingTrackedPolicyComparison}
              onBack={returnToTrackedPolicyHistory}
              onClose={closeTrackedPolicyHistory}
            />
          ) : selectedTrackedPolicy ? (
            <TrackedPolicyHistoryPanel
              trackedPolicy={selectedTrackedPolicy}
              snapshots={trackedPolicySnapshots}
              selectedSnapshotIds={selectedSnapshotIds}
              isLoading={isLoadingTrackedPolicySnapshots}
              isComparing={isLoadingTrackedPolicyComparison}
              onToggleSnapshot={toggleTrackedPolicySnapshotSelection}
              onCompare={compareSelectedTrackedPolicySnapshots}
              onClose={closeTrackedPolicyHistory}
            />
          ) : (
            <>
              <AnalysisSummaryCard report={selectedReport} isLoadingReport={isLoadingReport} />
              <FlaggedClausesList report={selectedReport} />
            </>
          )}
        </div>
      </section>
    </main>
  );
}
