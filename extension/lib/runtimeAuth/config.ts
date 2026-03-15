import type { SupabaseAuthConfig } from "./types";

export const AUTH_SUPABASE_URL_STORAGE_KEY = "auth_supabase_url";
export const AUTH_SUPABASE_ANON_KEY_STORAGE_KEY = "auth_supabase_anon_key";

/**
 * Runtime auth config boundary:
 * resolves Supabase URL/anon key from runtime overrides first, then build-time
 * injected values.
 */
export async function resolveSupabaseAuthConfig(): Promise<SupabaseAuthConfig> {
  const stored = await chrome.storage.local.get([
    AUTH_SUPABASE_URL_STORAGE_KEY,
    AUTH_SUPABASE_ANON_KEY_STORAGE_KEY,
  ]);

  const buildTimeConfig = readBuildTimeSupabaseConfig();
  const supabaseUrl = normalizeSupabaseUrl(
    readString(stored[AUTH_SUPABASE_URL_STORAGE_KEY]) || buildTimeConfig.supabaseUrl,
  );
  const anonKey =
    readString(stored[AUTH_SUPABASE_ANON_KEY_STORAGE_KEY]) || buildTimeConfig.anonKey;

  if (!supabaseUrl || !anonKey) {
    throw new Error(
      "Extension auth is not configured. Set EXTENSION_SUPABASE_URL and EXTENSION_SUPABASE_ANON_KEY at build time, or store auth_supabase_url/auth_supabase_anon_key in chrome.storage.local.",
    );
  }
  if (!isValidAbsoluteHttpUrl(supabaseUrl)) {
    throw new Error(
      "Extension auth Supabase URL is invalid. Use project root URL format: https://<project-ref>.supabase.co",
    );
  }

  return {
    supabaseUrl,
    anonKey,
  };
}

function readBuildTimeSupabaseConfig(): SupabaseAuthConfig {
  return {
    supabaseUrl: normalizeSupabaseUrl(
      readString(
        (globalThis as unknown as { __EXTENSION_SUPABASE_URL__?: unknown })
          .__EXTENSION_SUPABASE_URL__,
      ),
    ),
    anonKey: readString(
      (globalThis as unknown as { __EXTENSION_SUPABASE_ANON_KEY__?: unknown })
        .__EXTENSION_SUPABASE_ANON_KEY__,
    ),
  };
}

function normalizeSupabaseUrl(value: string): string {
  const trimmed = value.trim().replace(/\/+$/, "");
  if (!trimmed) {
    return "";
  }

  try {
    const parsed = new URL(trimmed);
    // Common misconfiguration: using issuer/auth endpoint URL instead of project root.
    // Accept it, but normalize back to origin so authorize/user endpoints resolve correctly.
    if (/^\/auth\/v1(?:\/.*)?$/i.test(parsed.pathname)) {
      return parsed.origin;
    }

    return `${parsed.origin}${parsed.pathname === "/" ? "" : parsed.pathname}`;
  } catch {
    // Keep previous behavior of surfacing config error through caller when URL is unusable.
    return trimmed;
  }
}

function readString(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function isValidAbsoluteHttpUrl(value: string): boolean {
  try {
    const parsed = new URL(value);
    return parsed.protocol === "https:" || parsed.protocol === "http:";
  } catch {
    return false;
  }
}
