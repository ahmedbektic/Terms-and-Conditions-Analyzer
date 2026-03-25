import { afterEach, describe, expect, it, vi } from 'vitest';

import { proxyApiRequest, resolveBackendOrigin } from '../worker/index';

describe('Cloudflare edge worker proxy', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('uses the configured backend origin when present', () => {
    const backendOrigin = resolveBackendOrigin(
      {
        API_BACKEND_ORIGIN: 'https://terms-api.onrender.com/',
        ASSETS: { fetch: vi.fn() },
      },
      new URL('https://terms.example.workers.dev/api/v1/reports'),
    );

    expect(backendOrigin).toBe('https://terms-api.onrender.com');
  });

  it('falls back to the local backend origin for local worker preview', () => {
    const backendOrigin = resolveBackendOrigin(
      { ASSETS: { fetch: vi.fn() } },
      new URL('http://127.0.0.1:8787/api/v1/reports'),
    );

    expect(backendOrigin).toBe('http://127.0.0.1:8000');
  });

  it('rejects deployed requests when the backend origin is missing', () => {
    expect(() =>
      resolveBackendOrigin(
        { ASSETS: { fetch: vi.fn() } },
        new URL('https://terms.example.workers.dev/api/v1/reports'),
      ),
    ).toThrow(/API_BACKEND_ORIGIN/);
  });

  it('forwards API requests through the configured backend origin', async () => {
    const fetchMock = vi.fn(async (request: Request) => {
      expect(request.url).toBe('https://terms-api.onrender.com/api/v1/reports');
      expect(request.headers.get('authorization')).toBe('Bearer test-token');
      expect(request.headers.get('cf-connecting-ip')).toBe('198.51.100.45');
      expect(request.headers.get('x-real-ip')).toBe('198.51.100.45');
      expect(request.headers.get('x-forwarded-host')).toBe('terms.example.workers.dev');
      return new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    const response = await proxyApiRequest(
      new Request('https://terms.example.workers.dev/api/v1/reports', {
        method: 'POST',
        headers: {
          Authorization: 'Bearer test-token',
          'CF-Connecting-IP': '198.51.100.45',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ terms_text: 'Valid enough terms text for analysis.' }),
      }),
      {
        API_BACKEND_ORIGIN: 'https://terms-api.onrender.com',
        ASSETS: { fetch: vi.fn() },
      },
    );

    expect(fetchMock).toHaveBeenCalledOnce();
    expect(response.status).toBe(200);
    expect(response.headers.get('Cache-Control')).toBe('no-store');
    expect(response.headers.get('X-Content-Type-Options')).toBe('nosniff');
  });

  it('blocks unsupported methods before they reach the backend', async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    const response = await proxyApiRequest(
      new Request('https://terms.example.workers.dev/api/v1/reports', {
        method: 'DELETE',
      }),
      {
        API_BACKEND_ORIGIN: 'https://terms-api.onrender.com',
        ASSETS: { fetch: vi.fn() },
      },
    );

    expect(fetchMock).not.toHaveBeenCalled();
    expect(response.status).toBe(405);
  });
});
