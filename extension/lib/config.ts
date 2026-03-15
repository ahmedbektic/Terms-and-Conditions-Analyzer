/**
 * Extension runtime configuration defaults.
 * Keep these in one place so popup/background/content behavior does not drift.
 * Values can still be overridden at runtime where explicitly supported.
 */
export const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000/api/v1";
export const STORAGE_KEY_API_BASE_URL = "api_base_url";
export const DEFAULT_EXTRACTION_MIN_LENGTH = 200;
