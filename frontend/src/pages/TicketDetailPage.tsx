import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { regenerateTicketSummary } from "../api/ai";
import { deleteTicket, getTicket } from "../api/tickets";
import CategorySuggestion from "../components/ticket/CategorySuggestion";
import MessagesPanel from "../components/ticket/MessagesPanel";
import SuggestedSolutionsPanel from "../components/ticket/SuggestedSolutionsPanel";
import NotesThreadPanel from "../components/ticket/NotesThreadPanel";
import TicketHistoryPanel from "../components/ticket/TicketHistoryPanel";
import TicketWorkflowPanel from "../components/ticket/TicketWorkflowPanel";
import { ErrorBanner, Loading, StatusBadge, formatDateTime, styles, tokens } from "../components/ui";
import type { TicketDetail } from "../types/ticket";

// "Notes" sits next to "Messages" deliberately: same ticket, two audiences —
// the customer thread and the internal one.
const TABS = ["Overview", "Workflow", "Messages", "Notes", "History"] as const;
type Tab = (typeof TABS)[number];

export default function TicketDetailPage() {
  const { id = "" } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [ticket, setTicket] = useState<TicketDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState<Tab>("Overview");
  const [summaryBusy, setSummaryBusy] = useState(false);
  const [summaryError, setSummaryError] = useState<string | null>(null);

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

  async function handleRegenerateSummary() {
    setSummaryBusy(true);
    setSummaryError(null);
    try {
      const updated = await regenerateTicketSummary(id);
      setTicket((current) => (current ? { ...current, ...updated } : current));
    } catch (err) {
      // A failed regeneration must not blank the summary that's already
      // there, and must not crash the rest of the page.
      setSummaryError(err instanceof Error ? err.message : String(err));
    } finally {
      setSummaryBusy(false);
    }
  }

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

            <div style={{ ...styles.card, marginBottom: "1rem" }}>
              <div style={{ ...styles.row, justifyContent: "space-between" }}>
                <span style={{ ...styles.row, gap: "0.4rem" }}>
                  <strong>Summary</strong>
                  {/* Visible AI-generated label, per this arc's global rule —
                      every AI output is marked wherever it is shown. */}
                  <span
                    style={{
                      fontSize: "0.7rem",
                      textTransform: "uppercase",
                      letterSpacing: "0.05em",
                      padding: "0.1rem 0.4rem",
                      borderRadius: 8,
                      border: `1px solid ${tokens.accent}`,
                      color: tokens.accent,
                    }}
                  >
                    AI-generated
                  </span>
                </span>
                <button
                  type="button"
                  style={styles.button}
                  onClick={() => void handleRegenerateSummary()}
                  disabled={summaryBusy}
                >
                  {summaryBusy ? "Generating…" : ticket.ai_summary ? "Regenerate" : "Generate summary"}
                </button>
              </div>
              <ErrorBanner message={summaryError} />
              <p style={{ whiteSpace: "pre-wrap", margin: "0.5rem 0 0" }}>
                {ticket.ai_summary ?? "No summary yet."}
              </p>
              {ticket.ai_summary_generated_at && (
                <p style={{ ...styles.muted, margin: "0.35rem 0 0", fontSize: "0.8rem" }}>
                  Generated {formatDateTime(ticket.ai_summary_generated_at)}
                </p>
              )}
            </div>

            <dl>
              <dt style={styles.label}>Subject</dt>
              <dd style={{ margin: "0 0 0.75rem" }}>{ticket.subject}</dd>
              <dt style={styles.label}>Description</dt>
              <dd style={{ margin: "0 0 0.75rem", whiteSpace: "pre-wrap" }}>
                {ticket.description || "—"}
              </dd>
              <dt style={styles.label}>Category</dt>
              <dd style={{ margin: "0 0 0.75rem" }}>
                {ticket.category?.name ?? "—"}
                <CategorySuggestion ticket={ticket} onChanged={() => void load()} />
              </dd>
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

            <SuggestedSolutionsPanel ticketId={id} />
          </section>
        )}

        {tab === "Workflow" && <TicketWorkflowPanel ticket={ticket} onChanged={() => void load()} />}

        {tab === "Messages" && <MessagesPanel ticketId={id} ticket={ticket} />}

        {tab === "Notes" && <NotesThreadPanel ticketId={id} />}

        {tab === "History" && <TicketHistoryPanel ticketId={id} />}
      </div>
    </main>
  );
}
