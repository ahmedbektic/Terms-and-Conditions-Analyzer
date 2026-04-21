import { PanelStateMessage } from '../../../components/ui/PanelStateMessage';
import { formatDashboardDate } from '../presentation/formatDashboardDate';
import type { DashboardTrackedPolicyComparison } from '../types';

interface TrackedPolicyComparePanelProps {
  comparison: DashboardTrackedPolicyComparison | null;
  isLoading: boolean;
  onBack: () => void;
  onClose: () => void;
}

function getDiffBlockClassName(changeType: string): string {
  if (changeType === 'added') {
    return 'tracked-compare-block tracked-compare-block-added';
  }
  if (changeType === 'removed') {
    return 'tracked-compare-block tracked-compare-block-removed';
  }
  return 'tracked-compare-block tracked-compare-block-unchanged';
}

export function TrackedPolicyComparePanel({
  comparison,
  isLoading,
  onBack,
  onClose,
}: TrackedPolicyComparePanelProps) {
  if (isLoading) {
    return (
      <section className="panel">
        <header className="panel-header">
          <h2 className="panel-title">Policy Comparison</h2>
        </header>
        <PanelStateMessage message="Preparing policy comparison..." />
      </section>
    );
  }

  if (!comparison) {
    return null;
  }

  return (
    <section className="panel">
      <header className="panel-header panel-header-tight">
        <div className="tracked-history-header">
          <div>
            <h2 className="panel-title">Policy Comparison</h2>
            <p className="panel-description">
              Older and newer stored versions for {comparison.trackedPolicy.displayName}.
            </p>
          </div>
          <div className="tracked-compare-header-actions">
            <button type="button" className="button-secondary" onClick={onBack}>
              Back to history
            </button>
            <button type="button" className="button-secondary" onClick={onClose}>
              Back to report summary
            </button>
          </div>
        </div>
      </header>

      <div className="tracked-compare-meta-grid">
        <section className="tracked-compare-meta-card">
          <span className="tracked-compare-meta-label">Older version</span>
          <strong>Stored version #{comparison.olderSnapshot.versionNumber}</strong>
          <span className="watchlist-meta">
            Captured {formatDashboardDate(comparison.olderSnapshot.capturedAt)}
          </span>
          <span className="watchlist-url">
            {comparison.olderSnapshot.finalUrl ?? comparison.olderSnapshot.sourceUrl ?? 'Unknown URL'}
          </span>
        </section>
        <section className="tracked-compare-meta-card">
          <span className="tracked-compare-meta-label">Newer version</span>
          <strong>Stored version #{comparison.newerSnapshot.versionNumber}</strong>
          <span className="watchlist-meta">
            Captured {formatDashboardDate(comparison.newerSnapshot.capturedAt)}
          </span>
          <span className="watchlist-url">
            {comparison.newerSnapshot.finalUrl ?? comparison.newerSnapshot.sourceUrl ?? 'Unknown URL'}
          </span>
        </section>
      </div>

      {comparison.comparisonOutcome === 'no_meaningful_changes' ? (
        <div className="tracked-compare-empty-state">
          <p>No meaningful differences were found after normalizing the stored versions.</p>
          {comparison.normalizationNotice ? (
            <p className="muted">{comparison.normalizationNotice}</p>
          ) : null}
        </div>
      ) : (
        <>
          <div className="tracked-compare-columns" aria-hidden>
            <span>Older version</span>
            <span>Newer version</span>
          </div>

          <ul className="tracked-compare-list">
            {comparison.diffBlocks.map((block, index) => (
              <li key={`${block.changeType}-${index}`} className={getDiffBlockClassName(block.changeType)}>
                <div className="tracked-compare-cell tracked-compare-cell-older">
                  {block.olderText ? <p>{block.olderText}</p> : <span className="muted">No text in this block.</span>}
                </div>
                <div className="tracked-compare-cell tracked-compare-cell-newer">
                  {block.newerText ? <p>{block.newerText}</p> : <span className="muted">No text in this block.</span>}
                </div>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
