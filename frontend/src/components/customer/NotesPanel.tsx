import { useCallback, useEffect, useState } from "react";

import { createNote, deleteNote, listNotes, updateNote } from "../../api/customers";
import type { Note } from "../../types/customer";
import { ErrorBanner, Loading, formatDateTime, styles } from "../ui";

interface Props {
  customerId: string;
  archived: boolean;
  /** Bumped by the parent so the attachment panel can refresh after note edits. */
  onNotesChanged?: () => void;
}

export default function NotesPanel({ customerId, archived, onNotesChanged }: Props) {
  const [notes, setNotes] = useState<Note[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editBody, setEditBody] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setNotes(await listNotes(customerId));
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
      await createNote(customerId, draft);
      setDraft("");
      await load();
      onNotesChanged?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function saveEdit(note: Note) {
    setBusy(true);
    setError(null);
    try {
      await updateNote(note.id, editBody);
      setEditingId(null);
      await load();
      onNotesChanged?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete(note: Note) {
    setBusy(true);
    setError(null);
    try {
      await deleteNote(note.id);
      await load();
      // Deleting a note cascades its attachments server-side.
      onNotesChanged?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <h2 style={{ fontSize: "1.1rem" }}>Notes</h2>
      <ErrorBanner message={error} />

      {loading ? (
        <Loading />
      ) : notes.length === 0 ? (
        <p style={styles.muted}>No notes yet.</p>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {notes.map((note) => (
            <li key={note.id} style={styles.card}>
              {editingId === note.id ? (
                <>
                  <textarea
                    aria-label="Edit note"
                    rows={4}
                    value={editBody}
                    onChange={(event) => setEditBody(event.target.value)}
                    style={{ ...styles.input, width: "100%" }}
                  />
                  <div style={{ ...styles.row, marginTop: "0.5rem" }}>
                    <button
                      type="button"
                      style={styles.button}
                      disabled={busy || editBody.trim() === ""}
                      onClick={() => void saveEdit(note)}
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
                </>
              ) : (
                <>
                  <p style={{ whiteSpace: "pre-wrap", margin: 0 }}>{note.body}</p>
                  <div
                    style={{
                      ...styles.row,
                      justifyContent: "space-between",
                      marginTop: "0.5rem",
                    }}
                  >
                    <span style={styles.muted}>
                      updated {formatDateTime(note.updated_at)}
                    </span>
                    <span style={styles.row}>
                      <button
                        type="button"
                        style={styles.button}
                        onClick={() => {
                          setEditingId(note.id);
                          setEditBody(note.body);
                        }}
                        aria-label={`Edit note ${note.id}`}
                      >
                        Edit
                      </button>
                      <button
                        type="button"
                        style={styles.button}
                        disabled={busy}
                        onClick={() => void handleDelete(note)}
                        aria-label={`Delete note ${note.id}`}
                      >
                        Delete
                      </button>
                    </span>
                  </div>
                </>
              )}
            </li>
          ))}
        </ul>
      )}

      {archived ? (
        <p style={styles.muted}>This customer is archived — new notes cannot be added.</p>
      ) : (
        <form onSubmit={handleAdd} style={{ ...styles.card, marginTop: "1rem" }}>
          <h3 style={{ fontSize: "0.95rem", marginTop: 0 }}>Add note</h3>
          <textarea
            aria-label="New note"
            placeholder="Write a note…"
            rows={3}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            style={{ ...styles.input, width: "100%" }}
          />
          <button
            type="submit"
            style={{ ...styles.button, marginTop: "0.5rem" }}
            disabled={busy || draft.trim() === ""}
          >
            Add note
          </button>
        </form>
      )}
    </section>
  );
}
