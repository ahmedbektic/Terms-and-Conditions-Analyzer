/* Maps backend API response contracts into dashboard view models.
 * Keeping this centralized avoids leaking transport field names across components.
 */

import type {
  ReportListItemResponse,
  ReportResponse,
  TrackedPolicyResponse,
} from '../../lib/api/contracts';
import type {
  DashboardFlaggedClause,
  DashboardReport,
  DashboardReportListItem,
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
    createdAt: response.created_at,
  };
}
