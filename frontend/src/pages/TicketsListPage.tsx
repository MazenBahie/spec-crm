import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { listAgents, listTickets } from "../api/tickets";
import { TICKET_PRIORITIES, TICKET_STATUSES } from "../types/ticket";
import type { Agent, Ticket, TicketPriority, TicketStatus } from "../types/ticket";
import { ErrorBanner, Loading, formatDateTime, styles, tokens } from "../components/ui";

const PAGE_SIZE = 20;
const SEARCH_DEBOUNCE_MS = 300;

export default function TicketsListPage() {
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [status, setStatus] = useState<TicketStatus | "">("");
  const [priority, setPriority] = useState<TicketPriority | "">("");
  const [assigneeId, setAssigneeId] = useState("");
  const [unassignedOnly, setUnassignedOnly] = useState(false);
  const [offset, setOffset] = useState(0);

  const [items, setItems] = useState<Ticket[]>([]);
  const [total, setTotal] = useState(0);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listAgents().then(setAgents).catch(() => setAgents([]));
  }, []);

  // Debounce the search box so typing does not fire a request per keystroke.
  useEffect(() => {
    const timer = window.setTimeout(() => {
      setDebouncedSearch(search);
      setOffset(0);
    }, SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [search]);

  // Ignore responses from superseded requests so a slow early fetch cannot
  // overwrite a newer one.
  const requestId = useRef(0);

  const load = useCallback(async () => {
    const id = ++requestId.current;
    setLoading(true);
    setError(null);
    try {
      const page = await listTickets({
        q: debouncedSearch || undefined,
        status: status || undefined,
        priority: priority || undefined,
        assignee_id: unassignedOnly ? undefined : assigneeId || undefined,
        unassigned: unassignedOnly || undefined,
        limit: PAGE_SIZE,
        offset,
      });
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
  }, [debouncedSearch, status, priority, assigneeId, unassignedOnly, offset]);

  useEffect(() => {
    void load();
  }, [load]);

  function agentName(id: string | null): string {
    if (!id) return "Unassigned";
    return agents.find((a) => a.id === id)?.display_name ?? "Unassigned";
  }

  const page = Math.floor(offset / PAGE_SIZE) + 1;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <main style={styles.page}>
      <div style={{ ...styles.row, justifyContent: "space-between" }}>
        <div>
          <h1 style={styles.h1}>Tickets</h1>
          <p style={styles.muted}>{total} ticket(s) match the current filters.</p>
        </div>
        <div style={styles.row}>
          <Link to="/tickets/setup" style={{ ...styles.button, textDecoration: "none" }}>
            Setup
          </Link>
          <Link to="/tickets/new" style={{ ...styles.button, textDecoration: "none" }}>
            New ticket
          </Link>
        </div>
      </div>

      <div style={{ ...styles.row, marginTop: "1rem" }}>
        <input
          type="search"
          aria-label="Search tickets"
          placeholder="Search reference, subject, description…"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          style={{ ...styles.input, flex: "1 1 16rem" }}
        />
        <select
          aria-label="Filter by status"
          value={status}
          onChange={(event) => {
            setStatus(event.target.value as TicketStatus | "");
            setOffset(0);
          }}
          style={styles.input}
        >
          <option value="">All statuses</option>
          {TICKET_STATUSES.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
        <select
          aria-label="Filter by priority"
          value={priority}
          onChange={(event) => {
            setPriority(event.target.value as TicketPriority | "");
            setOffset(0);
          }}
          style={styles.input}
        >
          <option value="">All priorities</option>
          {TICKET_PRIORITIES.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
        <select
          aria-label="Filter by assignee"
          value={assigneeId}
          disabled={unassignedOnly}
          onChange={(event) => {
            setAssigneeId(event.target.value);
            setOffset(0);
          }}
          style={styles.input}
        >
          <option value="">All assignees</option>
          {agents.map((a) => (
            <option key={a.id} value={a.id}>
              {a.display_name}
              {a.is_active ? "" : " (inactive)"}
            </option>
          ))}
        </select>
        <label style={{ ...styles.row, gap: "0.25rem" }}>
          <input
            type="checkbox"
            checked={unassignedOnly}
            onChange={(event) => {
              setUnassignedOnly(event.target.checked);
              setOffset(0);
            }}
          />
          Unassigned only
        </label>
      </div>

      <ErrorBanner message={error} />

      {loading && items.length === 0 ? (
        <Loading />
      ) : items.length === 0 && !error ? (
        <p style={styles.muted}>No tickets match these filters.</p>
      ) : (
        <table style={styles.table}>
          <thead>
            <tr>
              <th style={styles.th}>Reference</th>
              <th style={styles.th}>Subject</th>
              <th style={styles.th}>Priority</th>
              <th style={styles.th}>Status</th>
              <th style={styles.th}>Assignee</th>
              <th style={styles.th}>Updated</th>
            </tr>
          </thead>
          <tbody>
            {items.map((ticket) => (
              <tr key={ticket.id}>
                <td style={styles.td}>
                  <Link to={`/tickets/${ticket.id}`}>{ticket.reference}</Link>
                </td>
                <td style={styles.td}>
                  {ticket.subject}
                  {ticket.is_overdue && (
                    <span style={{ color: tokens.danger, marginLeft: "0.4rem" }}>
                      overdue
                    </span>
                  )}
                </td>
                <td style={styles.td}>{ticket.priority}</td>
                <td style={styles.td}>{ticket.status}</td>
                <td style={styles.td}>{agentName(ticket.assignee_id)}</td>
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
        <span style={styles.muted}>
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
