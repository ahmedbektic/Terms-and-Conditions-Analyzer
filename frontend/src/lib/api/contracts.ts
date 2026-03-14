/* Architecture note:
 * Layer: transport contracts.
 * Keep field names aligned with backend JSON to avoid accidental drift.
 */

export interface AgreementCreateRequest {
  title?: string | null;
  source_url?: string | null;
  agreed_at?: string | null;
  terms_text: string;
}

export interface AgreementResponse {
  id: string;
  title: string | null;
  source_url: string | null;
  agreed_at: string | null;
  created_at: string;
}

export interface AnalysisTriggerRequest {
  trigger: 'manual';
}

export interface ReportAnalyzeRequest {
  title?: string | null;
  source_url?: string | null;
  agreed_at?: string | null;
  terms_text?: string | null;
}

export interface FlaggedClauseResponse {
  clause_type: string;
  severity: string;
  excerpt: string;
  explanation: string;
}

export interface ReportResponse {
  id: string;
  agreement_id: string;
  source_type: string;
  source_value: string;
  raw_input_excerpt: string;
  status: string;
  summary: string;
  trust_score: number;
  model_name: string;
  flagged_clauses: FlaggedClauseResponse[];
  created_at: string;
  completed_at: string | null;
}

export interface ReportListItemResponse {
  id: string;
  agreement_id: string;
  source_type: string;
  source_value: string;
  status: string;
  trust_score: number;
  model_name: string;
  created_at: string;
}
