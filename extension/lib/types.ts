// extension/lib/types.ts
// Types that mirror backend schemas – used by popup and background.

export interface AnalyzeRequest {
  text: string;
}

export interface AnalysisResult {
  summary: string;
  reportId: string;
}

export interface AuthSession {
  token: string | null;
}
