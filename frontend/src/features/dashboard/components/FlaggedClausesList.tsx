import type { DashboardReport } from '../types';

interface FlaggedClausesListProps {
  report: DashboardReport | null;
}

export function FlaggedClausesList({ report }: FlaggedClausesListProps) {
  if (!report) {
    return (
      <section className="panel">
        <h2 className="panel-title">Flagged Clauses</h2>
        <p>Flagged clauses will appear after a report is selected.</p>
      </section>
    );
  }

  const clauses = report.flaggedClauses;
  return (
    <section className="panel">
      <h2 className="panel-title">Flagged Clauses</h2>
      {clauses.length === 0 ? (
        <p>No flagged clauses were identified for this report.</p>
      ) : (
        <ul className="clause-list">
          {clauses.map((clause, index) => (
            <li key={`${clause.clauseType}-${index}`} className="clause-item">
              <div className="clause-heading">
                <strong>{clause.clauseType.replaceAll('_', ' ')}</strong>
                <span className="pill">{clause.severity}</span>
              </div>
              <p className="muted">{clause.excerpt}</p>
              <p>{clause.explanation}</p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
