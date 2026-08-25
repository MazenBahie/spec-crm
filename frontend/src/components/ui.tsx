/** Minimal shared UI atoms and style tokens (no CSS framework in this story). */

import type { CSSProperties, ReactNode } from "react";

export const tokens = {
  font: "system-ui, sans-serif",
  border: "#ddd",
  muted: "#666",
  danger: "#b00020",
  accent: "#0b5cad",
  surface: "#f7f7f8",
};

export const styles: Record<string, CSSProperties> = {
  page: {
    fontFamily: tokens.font,
    maxWidth: 960,
    margin: "2rem auto",
    padding: "0 1rem",
    lineHeight: 1.5,
  },
  h1: { fontSize: "1.5rem", marginBottom: "0.25rem" },
  muted: { color: tokens.muted, marginTop: 0 },
  table: { width: "100%", borderCollapse: "collapse", marginTop: "1rem" },
  th: {
    textAlign: "left",
    borderBottom: `2px solid ${tokens.border}`,
    padding: "0.5rem 0.5rem 0.5rem 0",
    fontSize: "0.85rem",
    textTransform: "uppercase",
    letterSpacing: "0.04em",
    color: tokens.muted,
  },
  td: { borderBottom: `1px solid ${tokens.border}`, padding: "0.6rem 0.5rem 0.6rem 0" },
  input: {
    padding: "0.45rem 0.6rem",
    fontSize: "1rem",
    border: `1px solid ${tokens.border}`,
    borderRadius: 4,
    fontFamily: "inherit",
  },
  button: {
    padding: "0.45rem 0.9rem",
    fontSize: "0.95rem",
    border: `1px solid ${tokens.border}`,
    borderRadius: 4,
    background: "#fff",
    cursor: "pointer",
    fontFamily: "inherit",
  },
  row: { display: "flex", gap: "0.5rem", alignItems: "center", flexWrap: "wrap" },
  card: {
    border: `1px solid ${tokens.border}`,
    borderRadius: 6,
    padding: "0.75rem 1rem",
    marginBottom: "0.75rem",
  },
  label: { display: "block", fontSize: "0.85rem", color: tokens.muted, marginBottom: 2 },
};

export function ErrorBanner({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <p role="alert" style={{ color: tokens.danger }}>
      {message}
    </p>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const archived = status === "archived";
  return (
    <span
      style={{
        fontSize: "0.75rem",
        textTransform: "uppercase",
        letterSpacing: "0.05em",
        padding: "0.15rem 0.45rem",
        borderRadius: 10,
        border: `1px solid ${archived ? tokens.muted : tokens.accent}`,
        color: archived ? tokens.muted : tokens.accent,
      }}
    >
      {status}
    </span>
  );
}

export function Loading({ children = "Loading…" }: { children?: ReactNode }) {
  return <p style={{ color: tokens.muted }}>{children}</p>;
}

/** Locale-formatted timestamp; falls back to the raw string if unparseable. */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString();
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** `datetime-local` input value for a Date, in local time. */
export function toDateTimeLocal(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}`
  );
}
