import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { listCustomers } from "../api/customers";
import type { Customer, CustomerStatus } from "../types/customer";
import { ErrorBanner, Loading, StatusBadge, formatDateTime, styles } from "../components/ui";

const PAGE_SIZE = 20;
const SEARCH_DEBOUNCE_MS = 300;

export default function CustomersListPage() {
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [status, setStatus] = useState<CustomerStatus | "">("");
  const [offset, setOffset] = useState(0);

  const [items, setItems] = useState<Customer[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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
      const page = await listCustomers({
        q: debouncedSearch || undefined,
        status: status || undefined,
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
  }, [debouncedSearch, status, offset]);

  useEffect(() => {
    void load();
  }, [load]);

  const page = Math.floor(offset / PAGE_SIZE) + 1;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <main style={styles.page}>
      <div style={{ ...styles.row, justifyContent: "space-between" }}>
        <div>
          <h1 style={styles.h1}>Customers</h1>
          <p style={styles.muted}>{total} customer(s) match the current filters.</p>
        </div>
        <Link to="/customers/new" style={{ ...styles.button, textDecoration: "none" }}>
          New customer
        </Link>
      </div>

      <div style={{ ...styles.row, marginTop: "1rem" }}>
        <input
          type="search"
          aria-label="Search customers"
          placeholder="Search name or company…"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          style={{ ...styles.input, flex: "1 1 16rem" }}
        />
        <select
          aria-label="Filter by status"
          value={status}
          onChange={(event) => {
            setStatus(event.target.value as CustomerStatus | "");
            setOffset(0);
          }}
          style={styles.input}
        >
          <option value="">All statuses</option>
          <option value="active">Active</option>
          <option value="archived">Archived</option>
        </select>
      </div>

      <ErrorBanner message={error} />

      {loading && items.length === 0 ? (
        <Loading />
      ) : items.length === 0 && !error ? (
        <p style={styles.muted}>No customers yet. Create the first one.</p>
      ) : (
        <table style={styles.table}>
          <thead>
            <tr>
              <th style={styles.th}>Name</th>
              <th style={styles.th}>Company</th>
              <th style={styles.th}>Status</th>
              <th style={styles.th}>Updated</th>
            </tr>
          </thead>
          <tbody>
            {items.map((customer) => (
              <tr key={customer.id}>
                <td style={styles.td}>
                  <Link to={`/customers/${customer.id}`}>{customer.display_name}</Link>
                </td>
                <td style={styles.td}>{customer.company ?? "—"}</td>
                <td style={styles.td}>
                  <StatusBadge status={customer.status} />
                </td>
                <td style={styles.td}>{formatDateTime(customer.updated_at)}</td>
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
