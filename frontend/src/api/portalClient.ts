/**
 * Fetch wrapper for the customer portal.
 *
 * A separate module from `client.ts` on purpose (not a shared `request()`
 * parameterised by identity scheme): a portal page must never be able to
 * accidentally send `X-Agent-Id`, and an agent page must never be able to
 * send a portal bearer token, just by importing the wrong helper.
 */

import { portalAuthHeaders, clearPortalSession } from "./portalAuth";
import { ApiError, API_BASE } from "./client";

/** Pull the backend's `detail` out of an error body, falling back to the status. */
async function toApiError(res: Response): Promise<ApiError> {
  let detail = `Request failed: ${res.status}`;
  try {
    const body = (await res.json()) as { detail?: unknown };
    if (typeof body.detail === "string") {
      detail = body.detail;
    } else if (Array.isArray(body.detail)) {
      const first = body.detail[0] as { msg?: string } | undefined;
      if (first?.msg) detail = first.msg;
    }
  } catch {
    // Non-JSON body (e.g. a proxy error page); keep the status message.
  }
  return new ApiError(res.status, detail);
}

export async function requestPortal<T>(path: string, init?: RequestInit): Promise<T> {
  const identity = portalAuthHeaders();
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers:
      init?.body instanceof FormData
        ? { ...identity, ...(init.headers ?? {}) }
        : { "Content-Type": "application/json", ...identity, ...(init?.headers ?? {}) },
  });

  if (res.status === 401) {
    // The stored session is gone, expired, or was never valid. Drop it so
    // the next protected-route render redirects to /portal/login instead of
    // retrying a request that cannot succeed.
    clearPortalSession();
  }
  if (!res.ok) throw await toApiError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}
