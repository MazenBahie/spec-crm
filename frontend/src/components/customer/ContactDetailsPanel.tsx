import { useCallback, useEffect, useState } from "react";

import {
  createContact,
  deleteContact,
  listContacts,
  updateContact,
} from "../../api/customers";
import { CONTACT_KINDS } from "../../types/customer";
import type { ContactDetail, ContactKind } from "../../types/customer";
import { ErrorBanner, Loading, styles } from "../ui";

export default function ContactDetailsPanel({ customerId }: { customerId: string }) {
  const [contacts, setContacts] = useState<ContactDetail[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [kind, setKind] = useState<ContactKind>("phone");
  const [value, setValue] = useState("");
  const [label, setLabel] = useState("");
  const [isPrimary, setIsPrimary] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setContacts(await listContacts(customerId));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [customerId]);

  useEffect(() => {
    void load();
  }, [load]);

  /** A kind already has a primary — used to block the second one before submit. */
  const primaryKinds = new Set(
    contacts.filter((contact) => contact.is_primary).map((contact) => contact.kind),
  );
  const primaryTaken = primaryKinds.has(kind);

  async function handleAdd(event: React.FormEvent) {
    event.preventDefault();
    // Client-side guard mirroring the server's single-primary-per-kind rule, so
    // the operator gets feedback without a round trip. The API still enforces it.
    if (isPrimary && primaryTaken) {
      setError(`A primary ${kind} contact already exists. Demote it first.`);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await createContact(customerId, {
        kind,
        value: value.trim(),
        label: label.trim() || null,
        is_primary: isPrimary,
      });
      setValue("");
      setLabel("");
      setIsPrimary(false);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function togglePrimary(contact: ContactDetail) {
    const next = !contact.is_primary;
    if (next && primaryKinds.has(contact.kind)) {
      setError(`A primary ${contact.kind} contact already exists. Demote it first.`);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await updateContact(customerId, contact.id, { is_primary: next });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete(contact: ContactDetail) {
    setBusy(true);
    setError(null);
    try {
      await deleteContact(customerId, contact.id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <h2 style={{ fontSize: "1.1rem" }}>Contact details</h2>
      <ErrorBanner message={error} />

      {loading ? (
        <Loading />
      ) : contacts.length === 0 ? (
        <p style={styles.muted}>No contact details yet.</p>
      ) : (
        <table style={styles.table}>
          <thead>
            <tr>
              <th style={styles.th}>Kind</th>
              <th style={styles.th}>Value</th>
              <th style={styles.th}>Label</th>
              <th style={styles.th}>Primary</th>
              <th style={styles.th} />
            </tr>
          </thead>
          <tbody>
            {contacts.map((contact) => (
              <tr key={contact.id}>
                <td style={styles.td}>{contact.kind}</td>
                <td style={styles.td}>{contact.value}</td>
                <td style={styles.td}>{contact.label ?? "—"}</td>
                <td style={styles.td}>
                  <button
                    type="button"
                    style={styles.button}
                    disabled={busy}
                    onClick={() => void togglePrimary(contact)}
                    aria-label={`${contact.is_primary ? "Demote" : "Promote"} ${contact.value}`}
                  >
                    {contact.is_primary ? "Primary ✓" : "Make primary"}
                  </button>
                </td>
                <td style={styles.td}>
                  <button
                    type="button"
                    style={styles.button}
                    disabled={busy}
                    onClick={() => void handleDelete(contact)}
                    aria-label={`Delete ${contact.value}`}
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <form onSubmit={handleAdd} style={{ ...styles.card, marginTop: "1rem" }}>
        <h3 style={{ fontSize: "0.95rem", marginTop: 0 }}>Add contact</h3>
        <div style={styles.row}>
          <select
            aria-label="Contact kind"
            value={kind}
            onChange={(event) => setKind(event.target.value as ContactKind)}
            style={styles.input}
          >
            {CONTACT_KINDS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
          <input
            aria-label="Contact value"
            placeholder="Value"
            required
            value={value}
            onChange={(event) => setValue(event.target.value)}
            style={{ ...styles.input, flex: "1 1 12rem" }}
          />
          <input
            aria-label="Contact label"
            placeholder="Label (e.g. work)"
            value={label}
            onChange={(event) => setLabel(event.target.value)}
            style={styles.input}
          />
          <label style={{ ...styles.row, gap: "0.25rem" }}>
            <input
              type="checkbox"
              checked={isPrimary}
              disabled={primaryTaken}
              onChange={(event) => setIsPrimary(event.target.checked)}
            />
            Primary
          </label>
          <button type="submit" style={styles.button} disabled={busy || value.trim() === ""}>
            Add
          </button>
        </div>
        {primaryTaken && (
          <p style={{ ...styles.muted, marginBottom: 0 }}>
            A primary {kind} contact already exists — demote it to reassign.
          </p>
        )}
      </form>
    </section>
  );
}
