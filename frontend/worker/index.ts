/* Architecture note:
 * Cloudflare owns the edge layer for deployed frontend traffic.
 *
 * Responsibilities in this worker:
 * - proxy `/api/*` requests to the Render-hosted backend so browser API calls
 *   traverse Cloudflare before reaching the application layer
 * - preserve forwarding metadata needed for backend rate limiting
 * - serve the SPA asset bundle for all non-API requests through the ASSETS binding
 *
 * Non-responsibilities:
 * - business validation, auth, and persistence remain in the FastAPI backend
 * - this worker does not duplicate backend authorization or rate-limit logic
 */

interface AssetFetcher {
  fetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response>;
}

interface WorkerEnv {
  ASSETS: AssetFetcher;
  API_BACKEND_ORIGIN?: string;
}

interface StreamingRequestInit extends RequestInit {
  duplex?: "half";
}

const API_PATH_PREFIX = "/api/";
const LOCAL_BACKEND_ORIGIN = "http://127.0.0.1:8000";
const ALLOWED_API_METHODS = new Set(["GET", "POST", "OPTIONS"]);
const PROXY_RESPONSE_HEADERS = {
  "Cache-Control": "no-store",
  "X-Content-Type-Options": "nosniff",
  "X-Robots-Tag": "noindex, nofollow",
};

export default {
  async fetch(request: Request, env: WorkerEnv): Promise<Response> {
    const requestUrl = new URL(request.url);
    if (requestUrl.pathname.startsWith(API_PATH_PREFIX)) {
      return proxyApiRequest(request, env, requestUrl);
    }

    return env.ASSETS.fetch(request);
  },
};

export async function proxyApiRequest(
  request: Request,
  env: WorkerEnv,
  requestUrl = new URL(request.url),
): Promise<Response> {
  const method = request.method.toUpperCase();
  if (!ALLOWED_API_METHODS.has(method)) {
    return jsonResponse(
      { detail: `Method ${request.method} is not allowed at the edge proxy.` },
      { status: 405 },
    );
  }

  const backendOrigin = resolveBackendOrigin(env, requestUrl);
  const proxyUrl = new URL(`${requestUrl.pathname}${requestUrl.search}`, backendOrigin);
  const forwardedHeaders = buildForwardHeaders(request, requestUrl);
  const requestInit: StreamingRequestInit = {
    method: request.method,
    headers: forwardedHeaders,
    body: method === "GET" || method === "HEAD" ? undefined : request.body,
    redirect: "manual",
  };

  if (requestInit.body) {
    requestInit.duplex = "half";
  }

  const proxyRequest = new Request(proxyUrl.toString(), requestInit);

  const backendResponse = await fetch(proxyRequest);
  return withResponseHeaders(backendResponse, PROXY_RESPONSE_HEADERS);
}

export function resolveBackendOrigin(env: WorkerEnv, requestUrl: URL): string {
  const configuredOrigin = (env.API_BACKEND_ORIGIN ?? "").trim().replace(/\/+$/, "");
  if (configuredOrigin) {
    return configuredOrigin;
  }

  if (isLocalHostname(requestUrl.hostname)) {
    return LOCAL_BACKEND_ORIGIN;
  }

  throw new Error(
    "Cloudflare Worker API proxy is missing API_BACKEND_ORIGIN. " +
      "Set it in the Cloudflare Workers dashboard before deploying.",
  );
}

function buildForwardHeaders(request: Request, requestUrl: URL): Headers {
  const headers = new Headers(request.headers);
  const clientIp = request.headers.get("CF-Connecting-IP")?.trim();

  headers.delete("host");
  headers.set("X-Forwarded-Host", requestUrl.host);
  headers.set("X-Forwarded-Proto", requestUrl.protocol.replace(":", ""));

  if (clientIp) {
    headers.set("CF-Connecting-IP", clientIp);
    headers.set("X-Real-IP", clientIp);

    const existingForwardedFor = request.headers.get("X-Forwarded-For")?.trim();
    headers.set(
      "X-Forwarded-For",
      existingForwardedFor ? `${existingForwardedFor}, ${clientIp}` : clientIp,
    );
  }

  return headers;
}

function withResponseHeaders(response: Response, extraHeaders: Record<string, string>): Response {
  const headers = new Headers(response.headers);
  for (const [key, value] of Object.entries(extraHeaders)) {
    headers.set(key, value);
  }

  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

function jsonResponse(payload: object, init: ResponseInit): Response {
  return new Response(JSON.stringify(payload), {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...PROXY_RESPONSE_HEADERS,
    },
  });
}

function isLocalHostname(hostname: string): boolean {
  return hostname === "localhost" || hostname === "127.0.0.1" || hostname === "::1";
}
