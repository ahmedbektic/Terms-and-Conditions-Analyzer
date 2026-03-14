import { PanelStateMessage } from '../../../components/ui/PanelStateMessage';
import { formatDashboardDate } from '../presentation/formatDashboardDate';
import type { DashboardReport } from '../types';

interface AnalysisSummaryCardProps {
  report: DashboardReport | null;
  isLoadingReport: boolean;
}

interface ScoreDescriptor {
  toneClassName: string;
  label: string;
}

function getTrustScoreDescriptor(score: number): ScoreDescriptor {
  if (score >= 80) {
    return { toneClassName: 'score-tone-strong', label: 'Higher trust' };
  }
  if (score >= 60) {
    return { toneClassName: 'score-tone-moderate', label: 'Mixed signals' };
  }
  return { toneClassName: 'score-tone-risk', label: 'Elevated risk' };
}

export function AnalysisSummaryCard({ report, isLoadingReport }: AnalysisSummaryCardProps) {
  if (isLoadingReport) {
    return (
      <section className="panel">
        <header className="panel-header">
          <h2 className="panel-title">Analysis Summary</h2>
        </header>
        <PanelStateMessage message="Loading report..." />
      </section>
    );
  }

  if (!report) {
    return (
      <section className="panel">
        <header className="panel-header">
          <h2 className="panel-title">Analysis Summary</h2>
        </header>
        <PanelStateMessage message="Submit an agreement to generate your first report." />
      </section>
    );
  }

  const scoreDescriptor = getTrustScoreDescriptor(report.trustScore);
  const normalizedScore = Math.min(100, Math.max(0, report.trustScore));

  return (
    <section className="panel">
      <header className="panel-header panel-header-tight">
        <h2 className="panel-title">Analysis Summary</h2>
      </header>
      <div className="summary-content">
        <div className="score-row">
          <p className="score">Trust score: {report.trustScore} / 100</p>
          <span className={`chip score-chip ${scoreDescriptor.toneClassName}`}>
            {scoreDescriptor.label}
          </span>
        </div>
        <div className="score-meter" aria-hidden>
          <span
            className={`score-meter-fill ${scoreDescriptor.toneClassName}`}
            style={{ width: `${normalizedScore}%` }}
          />
        </div>
        <p className="summary-text">{report.summary}</p>
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
            <dd>{formatDashboardDate(report.createdAt)}</dd>
          </div>
        </dl>
      </div>
    </section>
  );
}
