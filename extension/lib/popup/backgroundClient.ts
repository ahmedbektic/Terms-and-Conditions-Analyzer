import type {
  PopupToBackgroundMessage,
  PopupToBackgroundResponse,
} from "../contract";

/**
 * Popup-side background transport wrapper.
 *
 * The popup remains a thin UI layer by delegating protocol validation and
 * runtime sendMessage edge cases to this module.
 */
export async function requestBackgroundExpected<
  TType extends PopupToBackgroundResponse["type"],
>(
  request: PopupToBackgroundMessage,
  expectedType: TType,
): Promise<Extract<PopupToBackgroundResponse, { ok: true; type: TType }>> {
  const response = await sendBackgroundMessage(request);
  if (!response.ok) {
    throw new Error(`[${response.payload.area}] ${response.payload.message}`);
  }
  if (response.type !== expectedType) {
    throw new Error(
      `[protocol] Unexpected response type "${response.type}" (expected "${expectedType}").`,
    );
  }
  return response as Extract<PopupToBackgroundResponse, { ok: true; type: TType }>;
}

function sendBackgroundMessage(
  request: PopupToBackgroundMessage,
): Promise<PopupToBackgroundResponse> {
  return new Promise((resolve) => {
    chrome.runtime.sendMessage(request, (response: PopupToBackgroundResponse) => {
      // Chrome reports transport failures through `lastError` instead of
      // rejecting a Promise, so normalize it into the shared error envelope.
      if (chrome.runtime.lastError) {
        resolve({
          ok: false,
          type: "error",
          payload: {
            area: "protocol",
            message:
              chrome.runtime.lastError.message ??
              "Chrome runtime message failed without an explicit error message.",
          },
        });
        return;
      }

      if (!response || typeof response !== "object") {
        resolve({
          ok: false,
          type: "error",
          payload: {
            area: "protocol",
            message: "No response was received from background.",
          },
        });
        return;
      }

      resolve(response);
    });
  });
}
