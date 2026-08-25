import { useCallback, useEffect, useState } from "react";
import { fetchHealth, type HealthResponse } from "../api/client";

export default function HealthPage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setHealth(await fetchHealth());
    } catch (err) {
      setHealth(null);
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <main
      style={{
        fontFamily: "system-ui, sans-serif",
        maxWidth: 640,
        margin: "4rem auto",
        padding: "0 1rem",
        lineHeight: 1.5,
      }}
    >
      <h1 style={{ fontSize: "1.5rem", marginBottom: "0.25rem" }}>CRM — System Health</h1>
      <p style={{ color: "#666", marginTop: 0 }}>Live status reported by the backend.</p>

      <button
        onClick={() => void load()}
        disabled={loading}
        style={{
          padding: "0.5rem 1rem",
          fontSize: "1rem",
          cursor: loading ? "default" : "pointer",
          marginBottom: "1rem",
        }}
      >
        {loading ? "Checking…" : "Refresh"}
      </button>

      {error !== null && (
        <p role="alert" style={{ color: "#b00020" }}>
          {error}
        </p>
      )}

      {health !== null && (
        <>
          <p>
            status: <strong>{health.status}</strong>
          </p>
          <pre
            style={{
              background: "#f5f5f5",
              padding: "1rem",
              overflowX: "auto",
              borderRadius: 4,
            }}
          >
            {JSON.stringify(health, null, 2)}
          </pre>
        </>
      )}
    </main>
  );
}
