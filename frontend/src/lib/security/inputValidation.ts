/* Architecture note:
 * Shared runtime validation for all user-controlled browser inputs. The backend
 * still enforces the authoritative rules; these helpers stop obviously invalid
 * payloads before they hit the network and keep web/extension behavior aligned.
 */

import type { AgreementCreateRequest, ReportAnalyzeRequest } from '../api/contracts';
import type { PasswordCredentials } from '../auth/contracts';

export const MAX_TITLE_LENGTH = 200;
export const MAX_SOURCE_URL_LENGTH = 2048;
export const MAX_TERMS_TEXT_LENGTH = 200_000;
export const MIN_TERMS_TEXT_LENGTH = 20;
export const MAX_EMAIL_LENGTH = 320;
export const MIN_PASSWORD_LENGTH = 8;
export const MAX_PASSWORD_LENGTH = 128;

const CONTROL_CHARACTER_PATTERN = /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g;
const UNSAFE_HTML_BLOCK_PATTERN =
  /<(script|style|iframe|object|embed|svg|noscript)\b[^>]*>[\s\S]*?<\/\1>/gi;
const HTML_TAG_PATTERN = /<[^>]+>/g;
const WHITESPACE_PATTERN = /\s+/g;
const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export function sanitizePasswordCredentials(
  credentials: PasswordCredentials,
): PasswordCredentials {
  const email = sanitizeEmailAddress(credentials.email);
  const password = sanitizePassword(credentials.password);
  return { email, password };
}

export function sanitizeReportAnalyzeInput(input: ReportAnalyzeRequest): ReportAnalyzeRequest {
  const title = sanitizeOptionalSingleLineText(input.title ?? null, {
    fieldName: 'Title',
    maxLength: MAX_TITLE_LENGTH,
  });
  const sourceUrl = sanitizeOptionalSourceUrl(input.source_url ?? null);
  const termsText = sanitizeOptionalTermsText(input.terms_text ?? null);
  const agreedAt = sanitizeOptionalIsoDateTime(input.agreed_at ?? null);

  if (!sourceUrl && !termsText) {
    throw new Error('Provide either a source URL or terms text.');
  }

  return {
    title,
    source_url: sourceUrl,
    agreed_at: agreedAt,
    terms_text: termsText,
  };
}

export function sanitizeAgreementCreateInput(
  input: AgreementCreateRequest,
): AgreementCreateRequest {
  return {
    title: sanitizeOptionalSingleLineText(input.title ?? null, {
      fieldName: 'Title',
      maxLength: MAX_TITLE_LENGTH,
    }),
    source_url: sanitizeOptionalSourceUrl(input.source_url ?? null),
    agreed_at: sanitizeOptionalIsoDateTime(input.agreed_at ?? null),
    terms_text: sanitizeTermsText(input.terms_text),
  };
}

export function validateUuid(value: string, fieldName: string): string {
  const normalized = sanitizeSingleLineText(value, { fieldName, maxLength: 64 }).toLowerCase();
  if (!UUID_PATTERN.test(normalized)) {
    throw new Error(`${fieldName} is invalid.`);
  }
  return normalized;
}

export function sanitizeTermsText(value: string): string {
  const normalized = sanitizeText(value);
  if (!normalized) {
    throw new Error('Agreement text cannot be blank.');
  }
  if (normalized.length < MIN_TERMS_TEXT_LENGTH) {
    throw new Error(`Agreement text must be at least ${MIN_TERMS_TEXT_LENGTH} characters.`);
  }
  if (normalized.length > MAX_TERMS_TEXT_LENGTH) {
    throw new Error(`Agreement text must be ${MAX_TERMS_TEXT_LENGTH} characters or fewer.`);
  }
  return normalized;
}

export function sanitizeOptionalTermsText(value: string | null): string | null {
  if (value === null) {
    return null;
  }
  const normalized = sanitizeText(value);
  if (!normalized) {
    return null;
  }
  return sanitizeTermsText(normalized);
}

export function sanitizeOptionalSourceUrl(value: string | null): string | null {
  if (value === null) {
    return null;
  }
  const normalized = sanitizeText(value);
  if (!normalized) {
    return null;
  }
  return validateExternalSourceUrl(normalized);
}

export function sanitizeOptionalSingleLineText(
  value: string | null,
  options: { fieldName: string; maxLength: number },
): string | null {
  if (value === null) {
    return null;
  }
  const normalized = sanitizeText(value);
  if (!normalized) {
    return null;
  }
  return sanitizeSingleLineText(normalized, options);
}

function sanitizeSingleLineText(
  value: string,
  options: { fieldName: string; maxLength: number; minLength?: number },
): string {
  const normalized = sanitizeText(value);
  if (!normalized) {
    throw new Error(`${options.fieldName} cannot be blank.`);
  }
  if (options.minLength && normalized.length < options.minLength) {
    throw new Error(`${options.fieldName} must be at least ${options.minLength} characters.`);
  }
  if (normalized.length > options.maxLength) {
    throw new Error(`${options.fieldName} must be ${options.maxLength} characters or fewer.`);
  }
  return normalized;
}

function validateExternalSourceUrl(value: string): string {
  if (value.length > MAX_SOURCE_URL_LENGTH) {
    throw new Error(`Source URL must be ${MAX_SOURCE_URL_LENGTH} characters or fewer.`);
  }

  let url: URL;
  try {
    url = new URL(value);
  } catch {
    throw new Error('Source URL must be a valid absolute URL.');
  }

  if (url.protocol !== 'http:' && url.protocol !== 'https:') {
    throw new Error('Source URL must use http or https.');
  }
  if (!url.hostname) {
    throw new Error('Source URL must include a hostname.');
  }
  if (url.username || url.password) {
    throw new Error('Source URL cannot include embedded credentials.');
  }
  if (isDisallowedHostname(url.hostname)) {
    throw new Error('Source URL must target a public hostname.');
  }

  url.hash = '';
  return url.toString();
}

function sanitizeOptionalIsoDateTime(value: string | null): string | null {
  if (value === null) {
    return null;
  }
  const normalized = sanitizeText(value);
  if (!normalized) {
    return null;
  }

  const date = new Date(normalized);
  if (Number.isNaN(date.getTime())) {
    throw new Error('Agreed date is invalid.');
  }
  if (date.getTime() > Date.now() + 24 * 60 * 60 * 1000) {
    throw new Error('Agreed date cannot be in the future.');
  }
  return date.toISOString();
}

function sanitizeEmailAddress(value: string): string {
  const normalized = sanitizeSingleLineText(value, {
    fieldName: 'Email',
    maxLength: MAX_EMAIL_LENGTH,
  }).toLowerCase();

  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(normalized)) {
    throw new Error('Email address is invalid.');
  }
  return normalized;
}

function sanitizePassword(value: string): string {
  const normalized = value.replace(CONTROL_CHARACTER_PATTERN, '');
  if (!normalized.trim()) {
    throw new Error('Password is required.');
  }
  if (normalized.length < MIN_PASSWORD_LENGTH) {
    throw new Error(`Password must be at least ${MIN_PASSWORD_LENGTH} characters.`);
  }
  if (normalized.length > MAX_PASSWORD_LENGTH) {
    throw new Error(`Password must be ${MAX_PASSWORD_LENGTH} characters or fewer.`);
  }
  return normalized;
}

function sanitizeText(value: string): string {
  return value
    .normalize('NFKC')
    .replace(CONTROL_CHARACTER_PATTERN, ' ')
    .replace(UNSAFE_HTML_BLOCK_PATTERN, ' ')
    .replace(HTML_TAG_PATTERN, ' ')
    .replace(WHITESPACE_PATTERN, ' ')
    .trim();
}

function isDisallowedHostname(hostname: string): boolean {
  const normalized = hostname.trim().replace(/\.$/, '').toLowerCase();
  if (!normalized) {
    return true;
  }
  if (normalized === 'localhost' || normalized === '0.0.0.0') {
    return true;
  }
  if (
    normalized.endsWith('.local') ||
    normalized.endsWith('.internal') ||
    normalized.endsWith('.localhost')
  ) {
    return true;
  }
  if (
    /^127\./.test(normalized) ||
    /^10\./.test(normalized) ||
    /^192\.168\./.test(normalized) ||
    /^169\.254\./.test(normalized)
  ) {
    return true;
  }
  if (/^172\.(1[6-9]|2\d|3[0-1])\./.test(normalized)) {
    return true;
  }
  if (normalized === '::1') {
    return true;
  }
  return false;
}
