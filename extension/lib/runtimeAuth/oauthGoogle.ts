import { AUTH_PROVIDER_GOOGLE } from "../../../frontend/src/lib/auth/providerErrors";

const PKCE_METHOD_S256 = "s256";

export interface GooglePkceFlowResult {
  authCode: string;
  codeVerifier: string;
}

/**
 * Starts Google OAuth through Supabase and returns the authorization code +
 * PKCE verifier for server-side token exchange.
 */
export async function launchGooglePkceOAuthFlow(
  supabaseUrl: string,
): Promise<GooglePkceFlowResult> {
  const codeVerifier = createPkceCodeVerifier();
  const codeChallenge = await createPkceCodeChallenge(codeVerifier);
  const redirectUrl = chrome.identity.getRedirectURL("supabase-auth");
  const authorizeUrl = new URL(`${supabaseUrl}/auth/v1/authorize`);
  authorizeUrl.searchParams.set("provider", AUTH_PROVIDER_GOOGLE);
  authorizeUrl.searchParams.set("redirect_to", redirectUrl);
  // PKCE code flow: do not set implicit-flow parameters (`response_type=token`).
  authorizeUrl.searchParams.set("code_challenge", codeChallenge);
  authorizeUrl.searchParams.set("code_challenge_method", PKCE_METHOD_S256);

  const callbackUrl = await launchWebAuthFlow(authorizeUrl.toString());
  const authCode = parseOAuthCallbackAuthorizationCode(callbackUrl);

  return {
    authCode,
    codeVerifier,
  };
}

function launchWebAuthFlow(url: string): Promise<string> {
  return new Promise((resolve, reject) => {
    chrome.identity.launchWebAuthFlow(
      {
        url,
        interactive: true,
      },
      (callbackUrl) => {
        if (chrome.runtime.lastError) {
          reject(
            new Error(
              chrome.runtime.lastError.message ??
                "Google sign-in failed without an explicit Chrome runtime error.",
            ),
          );
          return;
        }

        if (!callbackUrl) {
          reject(new Error("Google sign-in did not return an OAuth callback URL."));
          return;
        }

        resolve(callbackUrl);
      },
    );
  });
}

export function parseOAuthCallbackAuthorizationCode(callbackUrl: string): string {
  const url = new URL(callbackUrl);
  const queryError = url.searchParams.get("error");
  const queryErrorDetail = url.searchParams.get("error_description");
  const hashParams = new URLSearchParams(url.hash.startsWith("#") ? url.hash.slice(1) : "");

  const oauthError = queryError ?? hashParams.get("error");
  if (oauthError) {
    const detail = queryErrorDetail ?? hashParams.get("error_description") ?? oauthError;
    throw new Error(`Google sign-in failed: ${detail}`);
  }

  const authCode = url.searchParams.get("code");
  if (!authCode || !authCode.trim()) {
    throw new Error("Google sign-in did not return an authorization code.");
  }

  return authCode.trim();
}

function createPkceCodeVerifier(length = 56): string {
  const randomBytes = new Uint8Array(length);
  crypto.getRandomValues(randomBytes);
  return toBase64Url(randomBytes);
}

async function createPkceCodeChallenge(codeVerifier: string): Promise<string> {
  const digest = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(codeVerifier),
  );
  return toBase64Url(new Uint8Array(digest));
}

function toBase64Url(bytes: Uint8Array): string {
  let binary = "";
  for (let index = 0; index < bytes.length; index += 1) {
    binary += String.fromCharCode(bytes[index] ?? 0);
  }

  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}
