export interface SupabaseAuthConfig {
  supabaseUrl: string;
  anonKey: string;
}

export interface SupabaseAuthUser {
  id: string;
  email: string | null;
}

export interface SupabaseTokenPayload {
  access_token: string;
  refresh_token?: string | null;
  expires_in?: number | null;
  expires_at?: number | null;
  user?: {
    id?: string;
    email?: string | null;
  } | null;
}

export interface SupabaseSignUpPayload {
  session?: SupabaseTokenPayload | null;
  access_token?: string;
  refresh_token?: string | null;
  expires_in?: number | null;
  expires_at?: number | null;
  user?: {
    id?: string;
    email?: string | null;
  } | null;
}

// Shared JSON-body contract for Supabase REST calls.
// Keep this as one type so request options and payload producers stay aligned.
export type SupabaseJsonBody = Record<string, unknown>;

export type NormalizedCredentials = SupabaseJsonBody & {
  email: string;
  password: string;
};

// Persisted storage shape is intentionally tolerant because older storage entries
// may omit non-critical fields. SessionCodec normalizes this into the strict
// shared `AuthenticatedSession` contract before use.
export interface PersistedSessionShape {
  userId: string;
  accessToken: string;
  email?: string | null;
  expiresAt?: number | null;
}
