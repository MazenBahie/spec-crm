import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { getFeedback, getPortalTicket, listPortalTicketEvents, submitFeedback } from "../../api/portal";
import type { TicketFeedback } from "../../types/portal";
import type { Ticket, TicketEvent } from "../../types/ticket";
import { ErrorBanner, Loading, StatusBadge, formatDateTime, styles } from "../../components/ui";

const EVENT_SENTENCES: Record<string, (event: TicketEvent) => string> = {
  created: () => "Ticket created.",
  status_changed: (event) =>
    `Status changed from ${event.old_value ?? "—"} to ${event.new_value ?? "—"}.`,
};

function FeedbackForm({
  ticketId,
  existing,
  onSaved,
}: {
  ticketId: string;
  existing: TicketFeedback | null;
  onSaved: (feedback: TicketFeedback) => void;
}) {
  const [rating, setRating] = useState(existing?.rating ?? 5);
  const [comment, setComment] = useState(existing?.comment ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const saved = await submitFeedback(ticketId, { rating, comment: comment.trim() || null });
      onSaved(saved);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section style={{ ...styles.card, marginTop: "1rem" }}>
      <h2 style={{ fontSize: "1.1rem", marginTop: 0 }}>
        {existing ? "Edit your feedback" : "How did we do?"}
      </h2>
      <ErrorBanner message={error} />
      <form onSubmit={handleSubmit}>
        <div style={{ marginBottom: "0.75rem" }}>
          <label htmlFor="rating" style={styles.label}>
            Rating (1-5)
          </label>
          <select
            id="rating"
            value={rating}
            onChange={(event) => setRating(Number(event.target.value))}
            style={styles.input}
          >
            {[1, 2, 3, 4, 5].map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </div>
        <div style={{ marginBottom: "0.75rem" }}>
          <label htmlFor="comment" style={styles.label}>
            Comment (optional)
          </label>
          <textarea
            id="comment"
            rows={3}
            value={comment}
            onChange={(event) => setComment(event.target.value)}
            style={{ ...styles.input, width: "100%", fontFamily: "inherit" }}
          />
        </div>
        <button type="submit" style={styles.button} disabled={saving}>
          {saving ? "Saving…" : existing ? "Update feedback" : "Submit feedback"}
        </button>
      </form>
    </section>
  );
}

export default function PortalTicketDetailPage() {
  const { id = "" } = useParams<{ id: string }>();

  const [ticket, setTicket] = useState<Ticket | null>(null);
  const [events, setEvents] = useState<TicketEvent[]>([]);
  const [feedback, setFeedback] = useState<TicketFeedback | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const loadedTicket = await getPortalTicket(id);
      setTicket(loadedTicket);
      setEvents(await listPortalTicketEvents(id));
      const terminal = loadedTicket.status === "resolved" || loadedTicket.status === "closed";
      setFeedback(terminal ? await getFeedback(id) : null);
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
          <Link to="/portal/tickets">Back to your tickets</Link>
        </p>
      </main>
    );
  }

  const isTerminal = ticket.status === "resolved" || ticket.status === "closed";

  return (
    <main style={styles.page}>
      <p style={styles.muted}>
        <Link to="/portal/tickets">← Your tickets</Link>
      </p>

      <h1 style={{ ...styles.h1, marginBottom: "0.4rem" }}>
        {ticket.reference} <StatusBadge status={ticket.status} />
      </h1>
      <p style={styles.muted}>{ticket.subject}</p>

      <ErrorBanner message={error} />

      <dl>
        <dt style={styles.label}>Description</dt>
        <dd style={{ margin: "0 0 0.75rem", whiteSpace: "pre-wrap" }}>
          {ticket.description || "—"}
        </dd>
        <dt style={styles.label}>Priority</dt>
        <dd style={{ margin: "0 0 0.75rem" }}>{ticket.priority}</dd>
        <dt style={styles.label}>Created</dt>
        <dd style={{ margin: "0 0 0.75rem" }}>{formatDateTime(ticket.created_at)}</dd>
        <dt style={styles.label}>Last updated</dt>
        <dd style={{ margin: 0 }}>{formatDateTime(ticket.updated_at)}</dd>
      </dl>

      <h2 style={{ fontSize: "1.1rem" }}>History</h2>
      {/* The backend already restricts this response to customer-safe event
          types; this filter is a second, client-side belt-and-braces check
          so an unrecognised type never renders instead of failing silently. */}
      {(() => {
        const visible = events.filter((event) => event.event_type in EVENT_SENTENCES);
        return visible.length === 0 ? (
          <p style={styles.muted}>No history yet.</p>
        ) : (
          <ul style={{ paddingLeft: "1.25rem" }}>
            {visible.map((event) => (
              <li key={event.id} style={{ marginBottom: "0.4rem" }}>
                {EVENT_SENTENCES[event.event_type](event) + " "}
                <span style={styles.muted}>{formatDateTime(event.created_at)}</span>
              </li>
            ))}
          </ul>
        );
      })()}

      {isTerminal && (
        <FeedbackForm ticketId={id} existing={feedback} onSaved={setFeedback} />
      )}
    </main>
  );
}
