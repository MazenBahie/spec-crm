import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { deleteTicket, getTicket } from "../api/tickets";
import MessagesPanel from "../components/ticket/MessagesPanel";
import TicketHistoryPanel from "../components/ticket/TicketHistoryPanel";
import TicketWorkflowPanel from "../components/ticket/TicketWorkflowPanel";
import { ErrorBanner, Loading, StatusBadge, formatDateTime, styles, tokens } from "../components/ui";
import type { TicketDetail } from "../types/ticket";

const TABS = ["Overview", "Workflow", "Messages", "History"] as const;
type Tab = (typeof TABS)[number];

export default function TicketDetailPage() {
  const { id = "" } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [ticket, setTicket] = useState<TicketDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState<Tab>("Overview");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setTicket(await getTicket(id));
    } catch (err) {
      setTicket(null);
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleDelete() {
    if (!window.confirm("Delete this ticket and all of its history? This cannot be undone.")) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await deleteTicket(id);
      navigate("/tickets");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setBusy(false);
    }
  }

  if (loading) {
    return (
      <main style={styles.page}>
        <Loading />
      </main>
    );
  }

  if (!ticket) {
    return (
      <main style={styles.page}>
        <ErrorBanner message={error ?? "Ticket not found."} />
        <p>
          <Link to="/tickets">Back to tickets</Link>
        </p>
      </main>
    );
  }

  return (
    <main style={styles.page}>
      <p style={styles.muted}>
        <Link to="/tickets">← Tickets</Link>
        {" · "}
        <Link to={`/customers/${ticket.customer_id}`}>{ticket.customer.display_name}</Link>
      </p>

      <div style={{ ...styles.row, justifyContent: "space-between" }}>
        <div>
          <h1 style={{ ...styles.h1, marginBottom: "0.4rem" }}>
            {ticket.reference} <StatusBadge status={ticket.status} />
          </h1>
          <p style={styles.muted}>{ticket.subject}</p>
        </div>
        <div style={styles.row}>
          <Link to={`/tickets/${id}/edit`} style={{ ...styles.button, textDecoration: "none" }}>
            Edit
          </Link>
          <button
            type="button"
            style={{ ...styles.button, color: tokens.danger }}
            onClick={() => void handleDelete()}
            disabled={busy}
          >
            Delete
          </button>
        </div>
      </div>

      <ErrorBanner message={error} />

      <div
        role="tablist"
        style={{ ...styles.row, gap: 0, marginTop: "1rem", borderBottom: `1px solid ${tokens.border}` }}
      >
        {TABS.map((name) => (
          <button
            key={name}
            role="tab"
            type="button"
            aria-selected={tab === name}
            onClick={() => setTab(name)}
            style={{
              ...styles.button,
              border: "none",
              borderBottom: tab === name ? `2px solid ${tokens.accent}` : "2px solid transparent",
              borderRadius: 0,
              fontWeight: tab === name ? 600 : 400,
            }}
          >
            {name}
          </button>
        ))}
      </div>

      <div style={{ marginTop: "1rem" }}>
        {tab === "Overview" && (
          <section>
            <h2 style={{ fontSize: "1.1rem" }}>Overview</h2>
            <dl>
              <dt style={styles.label}>Subject</dt>
              <dd style={{ margin: "0 0 0.75rem" }}>{ticket.subject}</dd>
              <dt style={styles.label}>Description</dt>
              <dd style={{ margin: "0 0 0.75rem", whiteSpace: "pre-wrap" }}>
                {ticket.description || "—"}
              </dd>
              <dt style={styles.label}>Category</dt>
              <dd style={{ margin: "0 0 0.75rem" }}>{ticket.category?.name ?? "—"}</dd>
              <dt style={styles.label}>Priority</dt>
              <dd style={{ margin: "0 0 0.75rem" }}>{ticket.priority}</dd>
              <dt style={styles.label}>Assignee</dt>
              <dd style={{ margin: "0 0 0.75rem" }}>
                {ticket.assignee?.display_name ?? "Unassigned"}
                {ticket.assignee && !ticket.assignee.is_active ? " (inactive)" : ""}
              </dd>
              <dt style={styles.label}>Escalation level</dt>
              <dd style={{ margin: "0 0 0.75rem" }}>{ticket.escalation_level}</dd>
              {ticket.is_overdue && (
                <>
                  <dt style={styles.label}>Overdue</dt>
                  <dd style={{ margin: "0 0 0.75rem", color: tokens.danger }}>
                    Past due date ({formatDateTime(ticket.due_at)})
                  </dd>
                </>
              )}
              <dt style={styles.label}>Created</dt>
              <dd style={{ margin: "0 0 0.75rem" }}>{formatDateTime(ticket.created_at)}</dd>
              <dt style={styles.label}>Last updated</dt>
              <dd style={{ margin: 0 }}>{formatDateTime(ticket.updated_at)}</dd>
            </dl>
          </section>
        )}

        {tab === "Workflow" && <TicketWorkflowPanel ticket={ticket} onChanged={() => void load()} />}

        {tab === "Messages" && <MessagesPanel ticketId={id} />}

        {tab === "History" && <TicketHistoryPanel ticketId={id} />}
      </div>
    </main>
  );
}
