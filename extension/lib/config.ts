/**
 * Extension runtime configuration defaults.
 * Keep these in one place so popup/background/content behavior does not drift.
 * Values can still be overridden at runtime where explicitly supported.
 */
const FALLBACK_API_BASE_URL = "http://127.0.0.1:8000/api/v1";

// Build-time value injected by extension/scripts/build.mjs.
// We keep global access isolated here so runtime modules use typed exports.
const BUILD_TIME_API_BASE_URL = readString(
  (globalThis as unknown as { __EXTENSION_API_BASE_URL__?: unknown }).__EXTENSION_API_BASE_URL__,
);

export const DEFAULT_API_BASE_URL =
  normalizeApiBaseUrl(BUILD_TIME_API_BASE_URL) ?? FALLBACK_API_BASE_URL;
export const STORAGE_KEY_API_BASE_URL = "api_base_url";
export const STORAGE_KEY_EXTRACTION_MIN_LENGTH = "extraction_min_length";
export const DEFAULT_EXTRACTION_MIN_LENGTH = 200;

/**
 * Normalizes API base URLs from env/storage inputs to reduce local-dev drift.
 * Returns null for unsupported/invalid values so callers can safely fallback.
 */
export function normalizeApiBaseUrl(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }

  try {
    const parsed = new URL(trimmed);
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
      return null;
    }

    const normalizedPath = parsed.pathname.replace(/\/+$/, "");
    const pathname = normalizedPath === "/" ? "" : normalizedPath;
    return `${parsed.origin}${pathname}`;
  } catch {
    return null;
  }
}

function readString(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}
