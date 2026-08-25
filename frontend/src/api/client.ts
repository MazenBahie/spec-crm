/** Shared fetch helpers. All calls go to `/api`, proxied by Vite in dev. */

export const API_BASE = "/api";

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/** Pull the backend's `detail` out of an error body, falling back to the status. */
async function toApiError(res: Response): Promise<ApiError> {
  let detail = `Request failed: ${res.status}`;
  try {
    const body = (await res.json()) as { detail?: unknown };
    if (typeof body.detail === "string") {
      detail = body.detail;
    } else if (Array.isArray(body.detail)) {
      // FastAPI validation errors arrive as a list of {loc, msg}.
      const first = body.detail[0] as { msg?: string } | undefined;
      if (first?.msg) detail = first.msg;
    }
  } catch {
    // Non-JSON body (e.g. a proxy error page); keep the status message.
  }
  return new ApiError(res.status, detail);
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers:
      init?.body instanceof FormData
        ? init.headers
        : { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });

  if (!res.ok) throw await toApiError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export function buildQuery(params: Record<string, string | number | undefined | null>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      search.set(key, String(value));
    }
  }
  const query = search.toString();
  return query ? `?${query}` : "";
}

export interface HealthResponse {
  status: string;
  database?: string;
  detail?: string;
}

export async function fetchHealth(): Promise<HealthResponse> {
  const res = await fetch(`${API_BASE}/health`);
  if (!res.ok) throw new Error(`Health check failed: ${res.status}`);
  return (await res.json()) as HealthResponse;
}
