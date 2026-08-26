import { useCallback, useEffect, useState } from "react";

import { addTicketComment, listTicketEvents } from "../../api/tickets";
import type { TicketEvent } from "../../types/ticket";
import { ErrorBanner, Loading, formatDateTime, styles } from "../ui";

interface Props {
  ticketId: string;
}

/** One sentence per event type. Events are immutable — no edit or delete here. */
function describe(event: TicketEvent): string {
  switch (event.event_type) {
    case "created":
      return "Ticket created";
    case "status_changed":
      return `Status changed from ${event.old_value} to ${event.new_value}`;
    case "priority_changed":
      return `Priority changed from ${event.old_value} to ${event.new_value}`;
    case "category_changed":
      return event.old_value
        ? "Category changed"
        : "Category set";
    case "assigned":
      return event.old_value ? "Reassigned" : "Assigned";
    case "unassigned":
      return "Unassigned";
    case "escalated":
      return `Escalated to level ${event.new_value}`;
    case "commented":
      return "Comment added";
    default:
      return event.event_type;
  }
}

export default function TicketHistoryPanel({ ticketId }: Props) {
  const [events, setEvents] = useState<TicketEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [comment, setComment] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const page = await listTicketEvents(ticketId, { limit: 200 });
      setEvents(page.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [ticketId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleComment(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await addTicketComment(ticketId, comment);
      setComment("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <h2 style={{ fontSize: "1.1rem" }}>History</h2>
      <ErrorBanner message={error} />

      {loading ? (
        <Loading />
      ) : events.length === 0 ? (
        <p style={styles.muted}>No history yet.</p>
      ) : (
        <ol style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {events.map((event) => (
            <li key={event.id} style={styles.card}>
              <div style={{ ...styles.row, justifyContent: "space-between" }}>
                <strong>{describe(event)}</strong>
                <span style={styles.muted}>{formatDateTime(event.created_at)}</span>
              </div>
              {event.comment && (
                <p style={{ whiteSpace: "pre-wrap", margin: "0.5rem 0 0" }}>{event.comment}</p>
              )}
              <p style={{ ...styles.muted, margin: "0.25rem 0 0" }}>
                {event.actor ?? "unattributed"}
              </p>
            </li>
          ))}
        </ol>
      )}

      <form onSubmit={handleComment} style={{ ...styles.card, marginTop: "1rem" }}>
        <h3 style={{ fontSize: "0.95rem", marginTop: 0 }}>Add comment</h3>
        <textarea
          aria-label="New comment"
          placeholder="Write a comment…"
          rows={3}
          value={comment}
          onChange={(event) => setComment(event.target.value)}
          style={{ ...styles.input, width: "100%" }}
        />
        <button
          type="submit"
          style={{ ...styles.button, marginTop: "0.5rem" }}
          disabled={busy || comment.trim() === ""}
        >
          Add comment
        </button>
      </form>
    </section>
  );
}
