import { FormEvent, useState } from 'react';

import { PanelStateMessage } from '../../../components/ui/PanelStateMessage';
import { sanitizeTrackedPolicyCreateInput } from '../../../lib/security/inputValidation';
import { formatDashboardDate } from '../presentation/formatDashboardDate';
import type { DashboardTrackedPolicy } from '../types';

interface TrackedPolicyWatchlistPanelProps {
  trackedPolicies: DashboardTrackedPolicy[];
  isLoadingTrackedPolicies: boolean;
  isCreatingTrackedPolicy: boolean;
  removingTrackedPolicyId: string | null;
  onCreateTrackedPolicy: (sourceUrl: string) => Promise<void>;
  onRemoveTrackedPolicy: (trackedPolicyId: string) => Promise<void>;
}

function getTrackingStatusChipClassName(trackingStatus: string): string {
  const normalizedStatus = trackingStatus.toLowerCase();
  if (normalizedStatus === 'active') {
    return 'tracking-status-active';
  }
  if (normalizedStatus === 'invalid_source') {
    return 'tracking-status-invalid';
  }
  if (normalizedStatus === 'pending_first_snapshot') {
    return 'tracking-status-pending';
  }
  return 'tracking-status-default';
}

function formatTrackingStatusLabel(trackingStatus: string): string {
  return trackingStatus.replace(/_/g, ' ');
}

export function TrackedPolicyWatchlistPanel({
  trackedPolicies,
  isLoadingTrackedPolicies,
  isCreatingTrackedPolicy,
  removingTrackedPolicyId,
  onCreateTrackedPolicy,
  onRemoveTrackedPolicy,
}: TrackedPolicyWatchlistPanelProps) {
  const [sourceUrl, setSourceUrl] = useState('');
  const [formError, setFormError] = useState<string | null>(null);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    try {
      const sanitizedInput = sanitizeTrackedPolicyCreateInput({
        source_url: sourceUrl,
      });
      setFormError(null);
      await onCreateTrackedPolicy(sanitizedInput.source_url);
      setSourceUrl('');
    } catch (error) {
      setFormError(error instanceof Error ? error.message : 'Source URL is invalid.');
    }
  };

  return (
    <section className="panel">
      <header className="panel-header panel-header-tight">
        <h2 className="panel-title">Policy Watchlist</h2>
        <p className="panel-description">
          Register legal page URLs for ongoing tracking. New entries are verified before they are
          saved.
        </p>
      </header>

      <form className="watchlist-form" onSubmit={handleSubmit}>
        <label className="field">
          <span>Policy URL</span>
          <input
            type="url"
            value={sourceUrl}
            onChange={(event) => setSourceUrl(event.target.value)}
            placeholder="https://example.com/legal/terms"
          />
        </label>
        <div className="actions watchlist-actions">
          <button type="submit" className="button-primary" disabled={isCreatingTrackedPolicy}>
            {isCreatingTrackedPolicy ? 'Adding...' : 'Add to watchlist'}
          </button>
          <p className="submit-hint">Only public, readable policy pages can be tracked.</p>
        </div>
      </form>

      {formError ? (
        <p className="inline-error watchlist-inline-error" role="alert">
          {formError}
        </p>
      ) : null}

      {isLoadingTrackedPolicies ? <PanelStateMessage message="Loading watchlist..." /> : null}
      {!isLoadingTrackedPolicies && trackedPolicies.length === 0 ? (
        <PanelStateMessage message="No tracked policies yet. Add a policy URL to start monitoring changes." />
      ) : null}

      <ul className="watchlist-list">
        {trackedPolicies.map((trackedPolicy) => (
          <li key={trackedPolicy.id} className="watchlist-row">
            <div className="watchlist-row-main">
              <div className="watchlist-row-copy">
                <strong className="watchlist-display-name">{trackedPolicy.displayName}</strong>
                <span className="watchlist-url">{trackedPolicy.canonicalUrl}</span>
                <span className="watchlist-meta">
                  {trackedPolicy.snapshotVersionCount} stored version
                  {trackedPolicy.snapshotVersionCount === 1 ? '' : 's'}
                  {' · '}
                  Last checked{' '}
                  {trackedPolicy.lastCheckedAt
                    ? formatDashboardDate(trackedPolicy.lastCheckedAt)
                    : 'Never'}
                </span>
              </div>
              <span
                className={`chip watchlist-status-chip ${getTrackingStatusChipClassName(
                  trackedPolicy.trackingStatus,
                )}`}
              >
                {formatTrackingStatusLabel(trackedPolicy.trackingStatus)}
              </span>
            </div>
            <div className="watchlist-row-actions">
              <button
                type="button"
                className="button-secondary"
                onClick={() => void onRemoveTrackedPolicy(trackedPolicy.id)}
                disabled={removingTrackedPolicyId === trackedPolicy.id}
              >
                {removingTrackedPolicyId === trackedPolicy.id ? 'Removing...' : 'Remove'}
              </button>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
