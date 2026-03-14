/* Architecture note:
 * This hook is the dashboard orchestration boundary. Presentational components
 * remain stateless, while this module coordinates API calls and UI states.
 */

import { useCallback, useState } from 'react';

import type { DashboardApiClient } from '../../../lib/api/client';
import { mapReport, mapReportListItem } from '../mappers';
import type {
  DashboardAnalysisInput,
  DashboardReport,
  DashboardReportListItem,
} from '../types';

interface UseDashboardReportsResult {
  selectedReport: DashboardReport | null;
  reportHistory: DashboardReportListItem[];
  isSubmitting: boolean;
  isLoadingHistory: boolean;
  isLoadingReport: boolean;
  errorMessage: string | null;
  successMessage: string | null;
  submitAndAnalyze: (input: DashboardAnalysisInput) => Promise<void>;
  loadReportHistory: () => Promise<void>;
  selectReport: (reportId: string) => Promise<void>;
  clearMessages: () => void;
}

/**
 * Dashboard state orchestrator used by the feature container.
 * Keeps network calls and status transitions out of presentational components.
 */
export function useDashboardReports(apiClient: DashboardApiClient): UseDashboardReportsResult {
  const [selectedReport, setSelectedReport] = useState<DashboardReport | null>(null);
  const [reportHistory, setReportHistory] = useState<DashboardReportListItem[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const [isLoadingReport, setIsLoadingReport] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const clearMessages = useCallback(() => {
    setErrorMessage(null);
    setSuccessMessage(null);
  }, []);

  const loadReportHistory = useCallback(async () => {
    setIsLoadingHistory(true);
    setErrorMessage(null);
    try {
      const reports = await apiClient.listReports();
      setReportHistory(reports.map(mapReportListItem));
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Failed to load report history.');
    } finally {
      setIsLoadingHistory(false);
    }
  }, [apiClient]);

  const submitAndAnalyze = useCallback(
    async (input: DashboardAnalysisInput) => {
      setIsSubmitting(true);
      setErrorMessage(null);
      setSuccessMessage(null);

      try {
        const report = await apiClient.submitAndAnalyze(input);
        setSelectedReport(mapReport(report));
        // Re-fetch list from backend as source of truth for persisted history ordering.
        const reports = await apiClient.listReports();
        setReportHistory(reports.map(mapReportListItem));
        setSuccessMessage('Analysis complete. Report has been saved.');
      } catch (error) {
        setErrorMessage(error instanceof Error ? error.message : 'Failed to analyze submission.');
      } finally {
        setIsSubmitting(false);
      }
    },
    [apiClient],
  );

  const selectReport = useCallback(
    async (reportId: string) => {
      setIsLoadingReport(true);
      setErrorMessage(null);
      setSuccessMessage(null);
      try {
        const report = await apiClient.getReport(reportId);
        setSelectedReport(mapReport(report));
      } catch (error) {
        setErrorMessage(error instanceof Error ? error.message : 'Failed to load report.');
      } finally {
        setIsLoadingReport(false);
      }
    },
    [apiClient],
  );

  return {
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
  };
}
