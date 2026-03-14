import type { DashboardReportListItem } from '../types';

interface ReportHistoryListProps {
  reports: DashboardReportListItem[];
  selectedReportId: string | null;
  isLoadingHistory: boolean;
  onSelectReport: (reportId: string) => Promise<void>;
}

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}

export function ReportHistoryList({
  reports,
  selectedReportId,
  isLoadingHistory,
  onSelectReport,
}: ReportHistoryListProps) {
  return (
    <section className="panel">
      <h2 className="panel-title">Saved Reports</h2>
      {isLoadingHistory ? <p>Loading report history...</p> : null}
      {!isLoadingHistory && reports.length === 0 ? (
        <p className="muted">No reports yet. Submit a terms agreement to create one.</p>
      ) : null}
      <ul className="history-list">
        {reports.map((report) => (
          <li key={report.id}>
            <button
              type="button"
              className={selectedReportId === report.id ? 'history-button selected' : 'history-button'}
              onClick={() => void onSelectReport(report.id)}
            >
              <span className="history-primary">
                <strong>{report.sourceType.toUpperCase()}</strong> {report.sourceValue}
              </span>
              <span className="history-secondary">
                Score {report.trustScore}/100 | {formatDate(report.createdAt)}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
