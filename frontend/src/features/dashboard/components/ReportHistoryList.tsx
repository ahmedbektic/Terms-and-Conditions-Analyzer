import { PanelStateMessage } from '../../../components/ui/PanelStateMessage';
import { formatDashboardDate } from '../presentation/formatDashboardDate';
import type { DashboardReportListItem } from '../types';

interface ReportHistoryListProps {
  reports: DashboardReportListItem[];
  selectedReportId: string | null;
  isLoadingHistory: boolean;
  onSelectReport: (reportId: string) => Promise<void>;
}

function getReportStatusChipClassName(status: string): string {
  const normalizedStatus = status.toLowerCase();
  if (normalizedStatus === 'completed') {
    return 'history-status-completed';
  }
  if (normalizedStatus === 'failed') {
    return 'history-status-failed';
  }
  if (normalizedStatus === 'pending' || normalizedStatus === 'running') {
    return 'history-status-pending';
  }
  return 'history-status-default';
}

export function ReportHistoryList({
  reports,
  selectedReportId,
  isLoadingHistory,
  onSelectReport,
}: ReportHistoryListProps) {
  return (
    <section className="panel">
      <header className="panel-header panel-header-tight">
        <h2 className="panel-title">Saved Reports</h2>
        <p className="panel-description">
          Select a report to view full details and flagged clauses.
        </p>
      </header>
      {isLoadingHistory ? (
        <PanelStateMessage message="Loading report history..." />
      ) : null}
      {!isLoadingHistory && reports.length === 0 ? (
        <PanelStateMessage message="No reports yet. Submit a terms agreement to create one." />
      ) : null}
      <ul className="history-list">
        {reports.map((report) => (
          <li key={report.id}>
            <button
              type="button"
              // Stable accessible label makes keyboard/screen-reader navigation predictable.
              aria-label={`${report.sourceType.toUpperCase()} ${report.sourceValue}`}
              className={selectedReportId === report.id ? 'history-button selected' : 'history-button'}
              onClick={() => void onSelectReport(report.id)}
            >
              <span className="history-primary-row">
                <span className="history-primary">
                  <strong className="history-source-type">{report.sourceType.toUpperCase()}</strong>
                  <span className="history-source-value">{report.sourceValue}</span>
                </span>
                <span className={`chip history-status-chip ${getReportStatusChipClassName(report.status)}`}>
                  {report.status}
                </span>
              </span>
              <span className="history-secondary">
                Score {report.trustScore}/100 | {formatDashboardDate(report.createdAt)}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
