import type { DashboardReport } from '../types';

interface AnalysisSummaryCardProps {
  report: DashboardReport | null;
  isLoadingReport: boolean;
}

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}

export function AnalysisSummaryCard({ report, isLoadingReport }: AnalysisSummaryCardProps) {
  if (isLoadingReport) {
    return (
      <section className="panel">
        <h2 className="panel-title">Analysis Summary</h2>
        <p>Loading report...</p>
      </section>
    );
  }

  if (!report) {
    return (
      <section className="panel">
        <h2 className="panel-title">Analysis Summary</h2>
        <p>Submit an agreement to generate your first report.</p>
      </section>
    );
  }

  return (
    <section className="panel">
      <h2 className="panel-title">Analysis Summary</h2>
      <p className="score">Trust score: {report.trustScore} / 100</p>
      <p>{report.summary}</p>
      <dl className="meta-grid">
        <div>
          <dt>Source type</dt>
          <dd>{report.sourceType}</dd>
        </div>
        <div>
          <dt>Source value</dt>
          <dd className="truncate">{report.sourceValue}</dd>
        </div>
        <div>
          <dt>Model</dt>
          <dd>{report.modelName}</dd>
        </div>
        <div>
          <dt>Created</dt>
          <dd>{formatDate(report.createdAt)}</dd>
        </div>
      </dl>
    </section>
  );
}
