import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { archiveCustomer, deleteCustomer, getCustomer } from "../api/customers";
import AttachmentsPanel from "../components/customer/AttachmentsPanel";
import ContactDetailsPanel from "../components/customer/ContactDetailsPanel";
import CustomerTicketsPanel from "../components/customer/CustomerTicketsPanel";
import InteractionsPanel from "../components/customer/InteractionsPanel";
import NotesPanel from "../components/customer/NotesPanel";
import { ErrorBanner, Loading, StatusBadge, formatDateTime, styles, tokens } from "../components/ui";
import type { CustomerDetail } from "../types/customer";

const TABS = ["Overview", "Contacts", "Interactions", "Tickets", "Notes & Attachments"] as const;
type Tab = (typeof TABS)[number];

export default function CustomerDetailPage() {
  const { id = "" } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [customer, setCustomer] = useState<CustomerDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState<Tab>("Overview");
  const [attachmentsReloadKey, setAttachmentsReloadKey] = useState(0);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setCustomer(await getCustomer(id));
    } catch (err) {
      setCustomer(null);
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleArchive() {
    setBusy(true);
    setError(null);
    try {
      await archiveCustomer(id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete() {
    // Hard delete cascades contacts, interactions, notes, and attachments.
    if (!window.confirm("Delete this customer and all of its history? This cannot be undone.")) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await deleteCustomer(id);
      navigate("/customers");
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

  if (!customer) {
    return (
      <main style={styles.page}>
        <ErrorBanner message={error ?? "Customer not found."} />
        <p>
          <Link to="/customers">Back to customers</Link>
        </p>
      </main>
    );
  }

  const archived = customer.status === "archived";

  return (
    <main style={styles.page}>
      <p style={styles.muted}>
        <Link to="/customers">← Customers</Link>
      </p>

      <div style={{ ...styles.row, justifyContent: "space-between" }}>
        <div>
          <h1 style={{ ...styles.h1, marginBottom: "0.4rem" }}>
            {customer.display_name} <StatusBadge status={customer.status} />
          </h1>
          <p style={styles.muted}>{customer.company ?? "No company recorded"}</p>
        </div>
        <div style={styles.row}>
          <Link to={`/customers/${id}/edit`} style={{ ...styles.button, textDecoration: "none" }}>
            Edit
          </Link>
          <button
            type="button"
            style={styles.button}
            onClick={() => void handleArchive()}
            disabled={busy || archived}
          >
            {archived ? "Archived" : "Archive"}
          </button>
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
              <dt style={styles.label}>Name</dt>
              <dd style={{ margin: "0 0 0.75rem" }}>{customer.display_name}</dd>
              <dt style={styles.label}>Company</dt>
              <dd style={{ margin: "0 0 0.75rem" }}>{customer.company ?? "—"}</dd>
              <dt style={styles.label}>Status</dt>
              <dd style={{ margin: "0 0 0.75rem" }}>
                {customer.status}
                {customer.archived_at
                  ? ` (since ${formatDateTime(customer.archived_at)})`
                  : ""}
              </dd>
              <dt style={styles.label}>Created</dt>
              <dd style={{ margin: "0 0 0.75rem" }}>{formatDateTime(customer.created_at)}</dd>
              <dt style={styles.label}>Last updated</dt>
              <dd style={{ margin: 0 }}>{formatDateTime(customer.updated_at)}</dd>
            </dl>
            {customer.contacts.length > 0 && (
              <p style={styles.muted}>
                {customer.contacts.length} contact detail(s) on file — see the Contacts tab.
              </p>
            )}
          </section>
        )}

        {tab === "Contacts" && <ContactDetailsPanel customerId={id} />}

        {tab === "Interactions" && <InteractionsPanel customerId={id} archived={archived} />}

        {tab === "Tickets" && <CustomerTicketsPanel customerId={id} archived={archived} />}

        {tab === "Notes & Attachments" && (
          <>
            <NotesPanel
              customerId={id}
              archived={archived}
              onNotesChanged={() => setAttachmentsReloadKey((key) => key + 1)}
            />
            <hr style={{ margin: "1.5rem 0", border: 0, borderTop: `1px solid ${tokens.border}` }} />
            <AttachmentsPanel customerId={id} reloadKey={attachmentsReloadKey} />
          </>
        )}
      </div>
    </main>
  );
}
