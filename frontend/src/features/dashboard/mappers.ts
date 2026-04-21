/* Maps backend API response contracts into dashboard view models.
 * Keeping this centralized avoids leaking transport field names across components.
 */

import type {
  ReportListItemResponse,
  ReportResponse,
  TrackedPolicyCreateResponse,
  TrackedPolicySnapshotComparisonResponse,
  TrackedPolicySnapshotResponse,
  TrackedPolicyResponse,
} from '../../lib/api/contracts';
import type {
  DashboardFlaggedClause,
  DashboardReport,
  DashboardReportListItem,
  DashboardTrackedPolicyComparison,
  DashboardTrackedPolicyComparisonBlock,
  DashboardTrackedPolicyEnrollmentResult,
  DashboardTrackedPolicySnapshot,
  DashboardTrackedPolicy,
} from './types';

function mapFlaggedClause(clause: ReportResponse['flagged_clauses'][number]): DashboardFlaggedClause {
  return {
    clauseType: clause.clause_type,
    severity: clause.severity,
    excerpt: clause.excerpt,
    explanation: clause.explanation,
  };
}

export function mapReport(response: ReportResponse): DashboardReport {
  return {
    id: response.id,
    agreementId: response.agreement_id,
    sourceType: response.source_type,
    sourceValue: response.source_value,
    rawInputExcerpt: response.raw_input_excerpt,
    status: response.status,
    summary: response.summary,
    trustScore: response.trust_score,
    modelName: response.model_name,
    flaggedClauses: response.flagged_clauses.map(mapFlaggedClause),
    createdAt: response.created_at,
    completedAt: response.completed_at,
    trackedPolicyId: response.tracked_policy_id,
    trackedPolicySnapshotId: response.tracked_policy_snapshot_id,
    trackedPolicyVersionNumber: response.tracked_policy_version_number,
  };
}

export function mapReportListItem(response: ReportListItemResponse): DashboardReportListItem {
  // Keep list-item mapping separate so future history payloads can diverge from detail payloads.
  return {
    id: response.id,
    agreementId: response.agreement_id,
    sourceType: response.source_type,
    sourceValue: response.source_value,
    status: response.status,
    trustScore: response.trust_score,
    modelName: response.model_name,
    createdAt: response.created_at,
    trackedPolicyId: response.tracked_policy_id,
    trackedPolicySnapshotId: response.tracked_policy_snapshot_id,
    trackedPolicyVersionNumber: response.tracked_policy_version_number,
  };
}

export function mapTrackedPolicy(response: TrackedPolicyResponse): DashboardTrackedPolicy {
  return {
    id: response.id,
    canonicalUrl: response.canonical_url,
    displayName: response.display_name,
    sourceType: response.source_type,
    trackingStatus: response.tracking_status,
    lastCheckedAt: response.last_checked_at,
    lastSuccessfulCaptureAt: response.last_successful_capture_at,
    latestCaptureStatus: response.latest_capture_status,
    latestCaptureMessage: response.latest_capture_message,
    latestChangeStatus: response.latest_change_status,
    latestChangeDetectedAt: response.latest_change_detected_at,
    createdAt: response.created_at,
    snapshotVersionCount: response.snapshot_version_count,
  };
}

export function mapTrackedPolicyEnrollmentResult(
  response: TrackedPolicyCreateResponse,
): DashboardTrackedPolicyEnrollmentResult {
  return {
    trackedPolicy: mapTrackedPolicy(response),
    baselineReportId: response.baseline_report_id,
    baselineReportAction: response.baseline_report_action,
  };
}

export function mapTrackedPolicySnapshot(
  response: TrackedPolicySnapshotResponse,
): DashboardTrackedPolicySnapshot {
  return {
    snapshotId: response.snapshot_id,
    versionNumber: response.version_number,
    capturedAt: response.captured_at,
    sourceUrl: response.source_url,
    finalUrl: response.final_url,
    captureStatus: response.capture_status,
    changeStatus: response.change_status,
  };
}

function mapTrackedPolicyComparisonBlock(
  response: TrackedPolicySnapshotComparisonResponse['diff_blocks'][number],
): DashboardTrackedPolicyComparisonBlock {
  return {
    changeType: response.change_type,
    olderText: response.older_text,
    newerText: response.newer_text,
  };
}

export function mapTrackedPolicyComparison(
  response: TrackedPolicySnapshotComparisonResponse,
): DashboardTrackedPolicyComparison {
  return {
    trackedPolicy: mapTrackedPolicy(response.tracked_policy),
    olderSnapshot: mapTrackedPolicySnapshot(response.older_snapshot),
    newerSnapshot: mapTrackedPolicySnapshot(response.newer_snapshot),
    diffBlocks: response.diff_blocks.map(mapTrackedPolicyComparisonBlock),
    comparisonOutcome: response.comparison_outcome,
    normalizationNotice: response.normalization_notice,
    renderMode: response.render_mode,
  };
}
