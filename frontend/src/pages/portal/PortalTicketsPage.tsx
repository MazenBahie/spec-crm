import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { listPortalTickets } from "../../api/portal";
import type { Ticket } from "../../types/ticket";
import { ErrorBanner, Loading, formatDateTime, styles } from "../../components/ui";

const PAGE_SIZE = 20;

export default function PortalTicketsPage() {
  const [offset, setOffset] = useState(0);
  const [items, setItems] = useState<Ticket[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Ignore responses from superseded requests so a slow early fetch cannot
  // overwrite a newer one -- same guard as TicketsListPage.
  const requestId = useRef(0);

  const load = useCallback(async () => {
    const id = ++requestId.current;
    setLoading(true);
    setError(null);
    try {
      const page = await listPortalTickets({ limit: PAGE_SIZE, offset });
      if (id !== requestId.current) return;
      setItems(page.items);
      setTotal(page.total);
    } catch (err) {
      if (id !== requestId.current) return;
      setItems([]);
      setTotal(0);
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      if (id === requestId.current) setLoading(false);
    }
  }, [offset]);

  useEffect(() => {
    void load();
  }, [load]);

  const page = Math.floor(offset / PAGE_SIZE) + 1;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <main style={styles.page}>
      <div style={{ ...styles.row, justifyContent: "space-between" }}>
        <div>
          <h1 style={styles.h1}>Your tickets</h1>
          <p style={styles.muted}>{total} ticket(s).</p>
        </div>
        <Link to="/portal/tickets/new" style={{ ...styles.button, textDecoration: "none" }}>
          New ticket
        </Link>
      </div>

      <ErrorBanner message={error} />

      {loading && items.length === 0 ? (
        <Loading />
      ) : items.length === 0 && !error ? (
        <p style={styles.muted}>You have not submitted any tickets yet.</p>
      ) : (
        <table style={styles.table}>
          <thead>
            <tr>
              <th style={styles.th}>Reference</th>
              <th style={styles.th}>Subject</th>
              <th style={styles.th}>Status</th>
              <th style={styles.th}>Priority</th>
              <th style={styles.th}>Updated</th>
            </tr>
          </thead>
          <tbody>
            {items.map((ticket) => (
              <tr key={ticket.id}>
                <td style={styles.td}>
                  <Link to={`/portal/tickets/${ticket.id}`}>{ticket.reference}</Link>
                </td>
                <td style={styles.td}>{ticket.subject}</td>
                <td style={styles.td}>{ticket.status}</td>
                <td style={styles.td}>{ticket.priority}</td>
                <td style={styles.td}>{formatDateTime(ticket.updated_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <div style={{ ...styles.row, marginTop: "1rem" }}>
        <button
          type="button"
          style={styles.button}
          onClick={() => setOffset((current) => Math.max(0, current - PAGE_SIZE))}
          disabled={offset === 0 || loading}
        >
          Previous
        </button>
        <span style={{ ...styles.muted, margin: 0 }}>
          Page {page} of {pageCount}
        </span>
        <button
          type="button"
          style={styles.button}
          onClick={() => setOffset((current) => current + PAGE_SIZE)}
          disabled={offset + PAGE_SIZE >= total || loading}
        >
          Next
        </button>
      </div>
    </main>
  );
}
