import * as Sentry from '@sentry/react';

const LOCAL_API_TRACE_TARGET = /^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?\/api\//;
const EDGE_API_TRACE_TARGET = /^\/api\//;
const FILTERED_VALUE = '[Filtered]';
const SERVICE_NAME = 'frontend-dashboard';
const SERVICE_SURFACE = 'react-dashboard';
const SENSITIVE_KEY_PARTS = [
  'authorization',
  'cookie',
  'token',
  'secret',
  'password',
  'apikey',
  'jwt',
];
const POLICY_TEXT_KEYS = new Set([
  'body',
  'requestbody',
  'termstext',
  'submittedtext',
  'normalizedtext',
  'normalizedtextbody',
  'rawtextbody',
  'capturedtext',
  'policytext',
  'rawpolicytext',
  'fullpolicytext',
  'rawinputexcerpt',
]);

function readEnvValue(value: string | undefined): string {
  return value?.trim() ?? '';
}

function resolveSentryEnvironment(): string {
  const configured = readEnvValue(import.meta.env.VITE_SENTRY_ENVIRONMENT);
  if (configured) {
    return configured;
  }

  return import.meta.env.MODE;
}

function resolveSentryTracesSampleRate(): number {
  const configured = readEnvValue(import.meta.env.VITE_SENTRY_TRACES_SAMPLE_RATE);
  if (!configured) {
    return 0;
  }

  const parsed = Number(configured);
  if (!Number.isFinite(parsed)) {
    return 0;
  }

  return Math.min(1, Math.max(0, parsed));
}

function buildCommonTags(
  environment: string,
  release: string,
): Record<string, string> {
  const tags: Record<string, string> = {
    service: SERVICE_NAME,
    service_surface: SERVICE_SURFACE,
    deployment_environment: environment,
  };

  if (release) {
    tags.release = release;
  }

  return tags;
}

function applyCommonTags(
  event: Sentry.Event,
  tags: Record<string, string>,
): Sentry.Event {
  event.tags = {
    ...tags,
    ...(event.tags ?? {}),
  };
  return event;
}

function scrubEvent(event: Sentry.Event): Sentry.Event {
  return scrubUnknown(event) as Sentry.Event;
}

function scrubBreadcrumb(breadcrumb: Sentry.Breadcrumb): Sentry.Breadcrumb {
  return scrubUnknown(breadcrumb) as Sentry.Breadcrumb;
}

function scrubUnknown(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map((item) => scrubUnknown(item));
  }

  if (!value || typeof value !== 'object') {
    if (typeof value === 'string' && value.trim().toLowerCase().startsWith('bearer ')) {
      return FILTERED_VALUE;
    }
    return value;
  }

  const scrubbedEntries = Object.entries(value).map(([key, entryValue]) => {
    if (shouldFilterKey(key)) {
      return [key, FILTERED_VALUE];
    }
    return [key, scrubUnknown(entryValue)];
  });

  return Object.fromEntries(scrubbedEntries);
}

function shouldFilterKey(key: string): boolean {
  const normalizedKey = key.toLowerCase().replace(/[^a-z0-9]+/g, '');
  if (POLICY_TEXT_KEYS.has(normalizedKey)) {
    return true;
  }
  return SENSITIVE_KEY_PARTS.some((part) => normalizedKey.includes(part));
}

export function initDashboardSentry(): boolean {
  const dsn = readEnvValue(import.meta.env.VITE_SENTRY_DSN);
  if (!dsn || typeof window === 'undefined') {
    return false;
  }
  const environment = resolveSentryEnvironment();
  const release = readEnvValue(import.meta.env.VITE_SENTRY_RELEASE);
  const commonTags = buildCommonTags(environment, release);

  Sentry.init({
    dsn,
    enabled: true,
    environment,
    release: release || undefined,
    tracesSampleRate: resolveSentryTracesSampleRate(),
    integrations: [Sentry.browserTracingIntegration()],
    tracePropagationTargets: [EDGE_API_TRACE_TARGET, LOCAL_API_TRACE_TARGET],
    sendDefaultPii: false,
    beforeSend(event) {
      return applyCommonTags(scrubEvent(event), commonTags);
    },
    beforeSendTransaction(event) {
      return applyCommonTags(scrubEvent(event), commonTags);
    },
    beforeBreadcrumb(breadcrumb) {
      return scrubBreadcrumb(breadcrumb);
    },
  });
  for (const [tagName, tagValue] of Object.entries(commonTags)) {
    Sentry.setTag(tagName, tagValue);
  }
  return true;
}
