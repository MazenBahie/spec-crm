export interface HealthResponse {
  status: string;
  database?: string;
  detail?: string;
}

export async function fetchHealth(): Promise<HealthResponse> {
  const res = await fetch("/api/health");
  if (!res.ok) throw new Error(`Health check failed: ${res.status}`);
  return (await res.json()) as HealthResponse;
}
