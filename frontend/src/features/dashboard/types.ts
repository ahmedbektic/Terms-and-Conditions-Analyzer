/* Architecture note:
 * Layer: feature view models.
 * These types decouple dashboard components from raw API contract shapes.
 */

import type { ReportAnalyzeRequest, TrackedPolicyCreateResponse } from '../../lib/api/contracts';

export type DashboardAnalysisInput = ReportAnalyzeRequest;

export interface DashboardFlaggedClause {
  clauseType: string;
  severity: string;
  excerpt: string;
  explanation: string;
}

export interface DashboardReport {
  id: string;
  agreementId: string;
  sourceType: string;
  sourceValue: string;
  rawInputExcerpt: string;
  status: string;
  summary: string;
  trustScore: number;
  modelName: string;
  flaggedClauses: DashboardFlaggedClause[];
  createdAt: string;
  completedAt: string | null;
  trackedPolicyId: string | null;
  trackedPolicySnapshotId: string | null;
  trackedPolicyVersionNumber: number | null;
}

export interface DashboardReportListItem {
  id: string;
  agreementId: string;
  sourceType: string;
  sourceValue: string;
  status: string;
  trustScore: number;
  modelName: string;
  createdAt: string;
  trackedPolicyId: string | null;
  trackedPolicySnapshotId: string | null;
  trackedPolicyVersionNumber: number | null;
}

export interface DashboardTrackedPolicy {
  id: string;
  canonicalUrl: string;
  displayName: string;
  sourceType: string;
  trackingStatus: string;
  lastCheckedAt: string | null;
  lastSuccessfulCaptureAt: string | null;
  latestCaptureStatus: string;
  latestCaptureMessage: string | null;
  createdAt: string;
  snapshotVersionCount: number;
}

export interface DashboardTrackedPolicyEnrollmentResult {
  trackedPolicy: DashboardTrackedPolicy;
  baselineReportId: string;
  baselineReportAction: TrackedPolicyCreateResponse['baseline_report_action'];
}
