import { useCallback, useEffect, useState } from "react";

import {
  createInteraction,
  deleteInteraction,
  listInteractions,
  updateInteraction,
} from "../../api/customers";
import { INTERACTION_KINDS } from "../../types/customer";
import type { Interaction, InteractionKind } from "../../types/customer";
import { ErrorBanner, Loading, formatDateTime, styles, toDateTimeLocal } from "../ui";

interface Props {
  customerId: string;
  archived: boolean;
}

export default function InteractionsPanel({ customerId, archived }: Props) {
  const [items, setItems] = useState<Interaction[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editSubject, setEditSubject] = useState("");
  const [editBody, setEditBody] = useState("");

  const [kind, setKind] = useState<InteractionKind>("call");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [occurredAt, setOccurredAt] = useState(() => toDateTimeLocal(new Date()));
  const [author, setAuthor] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const page = await listInteractions(customerId, { limit: 100 });
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

  async function handleAdd(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await createInteraction(customerId, {
        kind,
        subject: subject.trim() || null,
        body,
        // datetime-local has no zone; convert through Date to get an ISO instant.
        occurred_at: new Date(occurredAt).toISOString(),
        author: author.trim() || null,
      });
      setSubject("");
      setBody("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  function startEdit(interaction: Interaction) {
    setEditingId(interaction.id);
    setEditSubject(interaction.subject ?? "");
    setEditBody(interaction.body);
  }

  async function saveEdit(interaction: Interaction) {
    setBusy(true);
    setError(null);
    try {
      await updateInteraction(interaction.id, {
        subject: editSubject.trim() || null,
        body: editBody,
      });
      setEditingId(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete(interaction: Interaction) {
    setBusy(true);
    setError(null);
    try {
      await deleteInteraction(interaction.id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <h2 style={{ fontSize: "1.1rem" }}>Interaction history</h2>
      <ErrorBanner message={error} />

      {loading ? (
        <Loading />
      ) : items.length === 0 ? (
        <p style={styles.muted}>No interactions logged yet.</p>
      ) : (
        <ol style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {items.map((interaction) => (
            <li key={interaction.id} style={styles.card}>
              <div style={{ ...styles.row, justifyContent: "space-between" }}>
                <strong>
                  {interaction.kind}
                  {interaction.subject ? ` — ${interaction.subject}` : ""}
                </strong>
                <span style={styles.muted}>{formatDateTime(interaction.occurred_at)}</span>
              </div>

              {editingId === interaction.id ? (
                <div style={{ marginTop: "0.5rem" }}>
                  <input
                    aria-label="Edit subject"
                    value={editSubject}
                    onChange={(event) => setEditSubject(event.target.value)}
                    style={{ ...styles.input, width: "100%", marginBottom: "0.5rem" }}
                  />
                  <textarea
                    aria-label="Edit body"
                    value={editBody}
                    rows={3}
                    onChange={(event) => setEditBody(event.target.value)}
                    style={{ ...styles.input, width: "100%" }}
                  />
                  <div style={{ ...styles.row, marginTop: "0.5rem" }}>
                    <button
                      type="button"
                      style={styles.button}
                      disabled={busy}
                      onClick={() => void saveEdit(interaction)}
                    >
                      Save
                    </button>
                    <button
                      type="button"
                      style={styles.button}
                      onClick={() => setEditingId(null)}
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <>
                  {interaction.body && (
                    <p style={{ whiteSpace: "pre-wrap", margin: "0.5rem 0" }}>
                      {interaction.body}
                    </p>
                  )}
                  <div style={{ ...styles.row, justifyContent: "space-between" }}>
                    <span style={styles.muted}>{interaction.author ?? "unattributed"}</span>
                    <span style={styles.row}>
                      <button
                        type="button"
                        style={styles.button}
                        onClick={() => startEdit(interaction)}
                        aria-label={`Edit interaction ${interaction.subject ?? interaction.kind}`}
                      >
                        Edit
                      </button>
                      <button
                        type="button"
                        style={styles.button}
                        disabled={busy}
                        onClick={() => void handleDelete(interaction)}
                        aria-label={`Delete interaction ${interaction.subject ?? interaction.kind}`}
                      >
                        Delete
                      </button>
                    </span>
                  </div>
                </>
              )}
            </li>
          ))}
        </ol>
      )}

      {archived ? (
        <p style={styles.muted}>
          This customer is archived — new interactions cannot be logged.
        </p>
      ) : (
        <form onSubmit={handleAdd} style={{ ...styles.card, marginTop: "1rem" }}>
          <h3 style={{ fontSize: "0.95rem", marginTop: 0 }}>Log interaction</h3>
          <div style={styles.row}>
            <select
              aria-label="Interaction kind"
              value={kind}
              onChange={(event) => setKind(event.target.value as InteractionKind)}
              style={styles.input}
            >
              {INTERACTION_KINDS.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
            <input
              aria-label="Interaction subject"
              placeholder="Subject"
              value={subject}
              onChange={(event) => setSubject(event.target.value)}
              style={{ ...styles.input, flex: "1 1 12rem" }}
            />
            <input
              aria-label="Occurred at"
              type="datetime-local"
              required
              value={occurredAt}
              onChange={(event) => setOccurredAt(event.target.value)}
              style={styles.input}
            />
            <input
              aria-label="Author"
              placeholder="Author"
              value={author}
              onChange={(event) => setAuthor(event.target.value)}
              style={styles.input}
            />
          </div>
          <textarea
            aria-label="Interaction body"
            placeholder="What happened?"
            rows={3}
            value={body}
            onChange={(event) => setBody(event.target.value)}
            style={{ ...styles.input, width: "100%", marginTop: "0.5rem" }}
          />
          <button
            type="submit"
            style={{ ...styles.button, marginTop: "0.5rem" }}
            disabled={busy}
          >
            Add interaction
          </button>
        </form>
      )}
    </section>
  );
}
