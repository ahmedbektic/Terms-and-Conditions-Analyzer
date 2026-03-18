import type { SupabaseAuthConfig, SupabaseJsonBody } from "./types";

interface SupabaseRequestOptions {
  config: SupabaseAuthConfig;
  method: "GET" | "POST";
  endpoint: string;
  body: SupabaseJsonBody | undefined;
  accessToken: string | null;
}

export async function requestSupabaseJson<T>(options: SupabaseRequestOptions): Promise<T> {
  const headers = new Headers({
    apikey: options.config.anonKey,
  });

  if (options.body) {
    headers.set("Content-Type", "application/json");
  }
  if (options.accessToken) {
    headers.set("Authorization", `Bearer ${options.accessToken}`);
  }

  const response = await fetch(`${options.config.supabaseUrl}${options.endpoint}`, {
    method: options.method,
    headers,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });

  const rawText = await response.text();
  const payload = safeParseJson(rawText);

  if (!response.ok) {
    throw new Error(extractSupabaseErrorMessage(payload, response.status));
  }

  return payload as T;
}

function safeParseJson(text: string): unknown {
  if (!text.trim()) {
    return {};
  }
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return {};
  }
}

function extractSupabaseErrorMessage(payload: unknown, statusCode: number): string {
  if (typeof payload === "object" && payload !== null) {
    const withMessage = payload as {
      error_description?: unknown;
      msg?: unknown;
      message?: unknown;
      error?: unknown;
    };

    const messageCandidate =
      withMessage.error_description ??
      withMessage.msg ??
      withMessage.message ??
      withMessage.error;

    if (typeof messageCandidate === "string" && messageCandidate.trim()) {
      return messageCandidate;
    }
  }

  return `Supabase auth request failed with status ${statusCode}.`;
}
