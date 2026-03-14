import { PanelStateMessage } from '../../../components/ui/PanelStateMessage';
import type { DashboardReport } from '../types';

interface FlaggedClausesListProps {
  report: DashboardReport | null;
}

function getClauseSeverityChipClassName(severity: string): string {
  const normalizedSeverity = severity.toLowerCase();
  if (normalizedSeverity === 'high') {
    return 'severity-high';
  }
  if (normalizedSeverity === 'medium') {
    return 'severity-medium';
  }
  if (normalizedSeverity === 'low') {
    return 'severity-low';
  }
  return 'severity-default';
}

export function FlaggedClausesList({ report }: FlaggedClausesListProps) {
  if (!report) {
    return (
      <section className="panel">
        <header className="panel-header">
          <h2 className="panel-title">Flagged Clauses</h2>
        </header>
        <PanelStateMessage message="Flagged clauses will appear after a report is selected." />
      </section>
    );
  }

  const clauses = report.flaggedClauses;
  return (
    <section className="panel">
      <header className="panel-header panel-header-tight">
        <h2 className="panel-title">Flagged Clauses</h2>
      </header>
      {clauses.length === 0 ? (
        <PanelStateMessage message="No flagged clauses were identified for this report." />
      ) : (
        <>
          <p className="panel-description">
            {clauses.length} clause{clauses.length === 1 ? '' : 's'} flagged in this report.
          </p>
          <ul className="clause-list">
            {clauses.map((clause, index) => (
              <li key={`${clause.clauseType}-${index}`} className="clause-item">
                <div className="clause-heading">
                  <strong className="clause-title">{clause.clauseType.replaceAll('_', ' ')}</strong>
                  <span
                    className={`chip severity-chip ${getClauseSeverityChipClassName(clause.severity)}`}
                  >
                    {clause.severity}
                  </span>
                </div>
                <p className="clause-excerpt">{clause.excerpt}</p>
                <p className="clause-explanation">{clause.explanation}</p>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
