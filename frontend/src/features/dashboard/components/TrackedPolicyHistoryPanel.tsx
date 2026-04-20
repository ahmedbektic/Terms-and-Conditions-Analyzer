import { PanelStateMessage } from '../../../components/ui/PanelStateMessage';
import { formatDashboardDate } from '../presentation/formatDashboardDate';
import type { DashboardTrackedPolicy, DashboardTrackedPolicySnapshot } from '../types';

interface TrackedPolicyHistoryPanelProps {
  trackedPolicy: DashboardTrackedPolicy;
  snapshots: DashboardTrackedPolicySnapshot[];
  selectedSnapshotIds: string[];
  isLoading: boolean;
  isComparing: boolean;
  onToggleSnapshot: (snapshotId: string) => void;
  onCompare: () => Promise<void>;
  onClose: () => void;
}

function formatSnapshotChangeStatus(changeStatus: string | null): string | null {
  if (!changeStatus) {
    return null;
  }
  return changeStatus.replace(/_/g, ' ');
}

export function TrackedPolicyHistoryPanel({
  trackedPolicy,
  snapshots,
  selectedSnapshotIds,
  isLoading,
  isComparing,
  onToggleSnapshot,
  onCompare,
  onClose,
}: TrackedPolicyHistoryPanelProps) {
  const canCompare = selectedSnapshotIds.length === 2 && !isComparing;

  return (
    <section className="panel">
      <header className="panel-header panel-header-tight">
        <div className="tracked-history-header">
          <div>
            <h2 className="panel-title">Tracked Version History</h2>
            <p className="panel-description">
              Select two stored versions of {trackedPolicy.displayName} to compare.
            </p>
          </div>
          <button type="button" className="button-secondary" onClick={onClose}>
            Back to report summary
          </button>
        </div>
      </header>

      <div className="tracked-history-policy">
        <strong>{trackedPolicy.displayName}</strong>
        <span className="watchlist-url">{trackedPolicy.canonicalUrl}</span>
      </div>

      {isLoading ? <PanelStateMessage message="Loading stored version history..." /> : null}

      {!isLoading && snapshots.length === 0 ? (
        <PanelStateMessage message="No stored versions are available for this policy yet." />
      ) : null}

      {!isLoading && snapshots.length > 0 ? (
        <>
          {snapshots.length < 2 ? (
            <div className="panel-state panel-state-compact">
              <p className="state-text">
                This policy needs at least two stored versions before comparison is available.
              </p>
            </div>
          ) : null}

          <ul className="tracked-history-list">
            {snapshots.map((snapshot) => {
              const isSelected = selectedSnapshotIds.includes(snapshot.snapshotId);
              const changeStatusLabel = formatSnapshotChangeStatus(snapshot.changeStatus);

              return (
                <li key={snapshot.snapshotId}>
                  <label
                    className={
                      isSelected ? 'tracked-history-option tracked-history-option-selected' : 'tracked-history-option'
                    }
                  >
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => onToggleSnapshot(snapshot.snapshotId)}
                    />
                    <div className="tracked-history-option-copy">
                      <div className="tracked-history-option-header">
                        <strong>Stored version #{snapshot.versionNumber}</strong>
                        <span className="watchlist-meta">
                          {formatDashboardDate(snapshot.capturedAt)}
                        </span>
                      </div>
                      <span className="watchlist-meta">
                        Capture status: {snapshot.captureStatus.replace(/_/g, ' ')}
                      </span>
                      {changeStatusLabel ? (
                        <span className="watchlist-meta">Change status: {changeStatusLabel}</span>
                      ) : null}
                    </div>
                  </label>
                </li>
              );
            })}
          </ul>

          <div className="tracked-history-actions">
            <p className="field-help">
              {selectedSnapshotIds.length === 2
                ? 'Two stored versions selected. Compare them now.'
                : 'Select exactly two stored versions to enable comparison.'}
            </p>
            <button
              type="button"
              className="button-primary"
              disabled={!canCompare}
              onClick={() => void onCompare()}
            >
              {isComparing ? 'Comparing...' : 'Compare selected versions'}
            </button>
          </div>
        </>
      ) : null}
    </section>
  );
}
