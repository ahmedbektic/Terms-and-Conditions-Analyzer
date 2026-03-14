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

function resolveDashboardApiBaseUrl(): string {
  const configured = import.meta.env.VITE_API_BASE_URL;
  return configured ? String(configured) : 'http://localhost:8000/api/v1';
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
