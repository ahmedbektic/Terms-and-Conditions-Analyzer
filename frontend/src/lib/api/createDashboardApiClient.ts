/* Architecture note:
 * Factory for dashboard API clients used by web dashboard today and extension
 * surfaces later. Centralizing environment + token wiring here avoids
 * scattering transport setup across UI components.
 */

import { DashboardApiClient } from './client';

interface CreateDashboardApiClientOptions {
  getAccessToken?: () => string | null;
  fetchImpl?: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
}

const LOCAL_API_BASE_URL = 'http://127.0.0.1:8000/api/v1';
const EDGE_PROXY_API_BASE_URL = '/api/v1';

function isLocalHostname(hostname: string): boolean {
  return hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '::1';
}

function resolveDashboardApiBaseUrl(): string {
  const configured = import.meta.env.VITE_API_BASE_URL;
  const trimmedConfigured = configured ? String(configured).trim() : '';
  if (trimmedConfigured) {
    return trimmedConfigured;
  }

  if (typeof window !== 'undefined') {
    if (isLocalHostname(window.location.hostname)) {
      return LOCAL_API_BASE_URL;
    }

    console.warn(
      'VITE_API_BASE_URL is not set. Falling back to the same-origin Cloudflare edge proxy at /api/v1.',
    );
    return EDGE_PROXY_API_BASE_URL;
  }

  return LOCAL_API_BASE_URL;
}

export function createDashboardApiClient(
  options: CreateDashboardApiClientOptions = {},
): DashboardApiClient {
  return new DashboardApiClient({
    baseUrl: resolveDashboardApiBaseUrl(),
    getAccessToken: options.getAccessToken,
    fetchImpl: options.fetchImpl,
  });
}
