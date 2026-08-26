import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { listCustomerTickets } from "../../api/tickets";
import type { Ticket } from "../../types/ticket";
import { ErrorBanner, Loading, formatDateTime, styles } from "../ui";

interface Props {
  customerId: string;
  archived: boolean;
}

export default function CustomerTicketsPanel({ customerId, archived }: Props) {
  const [items, setItems] = useState<Ticket[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const page = await listCustomerTickets(customerId, { limit: 100 });
      setItems(page.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [customerId]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <section>
      <div style={{ ...styles.row, justifyContent: "space-between" }}>
        <h2 style={{ fontSize: "1.1rem" }}>Tickets</h2>
        {!archived && (
          <Link
            to={`/tickets/new?customerId=${customerId}`}
            style={{ ...styles.button, textDecoration: "none" }}
          >
            New ticket
          </Link>
        )}
      </div>
      <ErrorBanner message={error} />

      {loading ? (
        <Loading />
      ) : items.length === 0 ? (
        <p style={styles.muted}>No tickets for this customer yet.</p>
      ) : (
        <table style={styles.table}>
          <thead>
            <tr>
              <th style={styles.th}>Reference</th>
              <th style={styles.th}>Subject</th>
              <th style={styles.th}>Priority</th>
              <th style={styles.th}>Status</th>
              <th style={styles.th}>Updated</th>
            </tr>
          </thead>
          <tbody>
            {items.map((ticket) => (
              <tr key={ticket.id}>
                <td style={styles.td}>
                  <Link to={`/tickets/${ticket.id}`}>{ticket.reference}</Link>
                </td>
                <td style={styles.td}>{ticket.subject}</td>
                <td style={styles.td}>{ticket.priority}</td>
                <td style={styles.td}>{ticket.status}</td>
                <td style={styles.td}>{formatDateTime(ticket.updated_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
