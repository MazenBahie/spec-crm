import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { addNote, listNotes } from "../../api/notes";
import { listAgents } from "../../api/tickets";
import type { TicketNote } from "../../types/agent";
import type { Agent } from "../../types/ticket";
import { ErrorBanner, Loading, formatDateTime, styles, tokens } from "../ui";

interface Props {
  ticketId: string;
}

/** Same shape the backend resolves mentions with — see
 * `app.services.activity.MENTION_PATTERN`. */
const MENTION_PATTERN = /(@[A-Za-z0-9_.-]+)/g;

/** Split a note body so `@handle`s can be highlighted in place. */
function highlight(body: string) {
  return body.split(MENTION_PATTERN).map((part, index) =>
    part.startsWith("@") ? (
      <mark
        key={index}
        style={{ background: "transparent", color: tokens.accent, fontWeight: 600 }}
      >
        {part}
      </mark>
    ) : (
      <span key={index}>{part}</span>
    ),
  );
}

/** The handle an agent answers to, matching the backend's resolution rules. */
function handleFor(agent: Agent): string {
  const localPart = (agent.email ?? "").split("@")[0];
  return localPart || agent.display_name.replace(/\s+/g, "");
}

export default function NotesThreadPanel({ ticketId }: Props) {
  const [notes, setNotes] = useState<TicketNote[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [body, setBody] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const page = await listNotes(ticketId, { limit: 200 });
      setNotes(page.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [ticketId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    // Fetched once so the mention popover has something to offer. A dedicated
    // `GET /agents?q=` search endpoint would be worth it at a bigger roster.
    listAgents({ activeOnly: true })
      .then(setAgents)
      .catch(() => setAgents([]));
  }, []);

  /** The partial handle being typed, if the caret sits just after an `@word`. */
  const mentionQuery = useMemo(() => {
    const caret = textareaRef.current?.selectionStart ?? body.length;
    const match = /@([A-Za-z0-9_.-]*)$/.exec(body.slice(0, caret));
    return match ? match[1].toLowerCase() : null;
  }, [body]);

  const suggestions = useMemo(() => {
    if (mentionQuery === null) return [];
    return agents
      .filter(
        (agent) =>
          handleFor(agent).toLowerCase().startsWith(mentionQuery) ||
          agent.display_name.toLowerCase().includes(mentionQuery),
      )
      .slice(0, 5);
  }, [agents, mentionQuery]);

  function completeMention(agent: Agent) {
    setBody((current) => current.replace(/@([A-Za-z0-9_.-]*)$/, `@${handleFor(agent)} `));
    textareaRef.current?.focus();
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (body.trim() === "") return;
    setBusy(true);
    setError(null);
    try {
      const created = await addNote(ticketId, body);
      setNotes((current) => [...current, created]);
      setBody("");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby="notes-heading">
      <h2 id="notes-heading" style={{ fontSize: "1.1rem" }}>
        Notes (internal)
      </h2>
      <p style={styles.muted}>
        Only your team sees these. They are never sent to the customer.
      </p>

      <ErrorBanner message={error} />

      {loading ? (
        <Loading />
      ) : notes.length === 0 ? (
        <p style={styles.muted}>No internal notes on this ticket yet.</p>
      ) : (
        <ol style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {notes.map((note) => (
            <li key={note.id} style={styles.card}>
              <div style={{ ...styles.row, justifyContent: "space-between" }}>
                <strong>{note.author_display_name ?? "Unknown agent"}</strong>
                <span style={styles.muted}>{formatDateTime(note.created_at)}</span>
              </div>
              <p style={{ whiteSpace: "pre-wrap", margin: "0.5rem 0 0" }}>
                {highlight(note.body)}
              </p>
            </li>
          ))}
        </ol>
      )}

      <form onSubmit={handleSubmit} style={{ ...styles.card, marginTop: "1rem" }}>
        <h3 style={{ fontSize: "0.95rem", marginTop: 0 }}>Add a note</h3>
        <textarea
          ref={textareaRef}
          aria-label="Note body"
          placeholder="Type @ to mention a teammate…"
          rows={3}
          value={body}
          onChange={(event) => setBody(event.target.value)}
          style={{ ...styles.input, width: "100%", boxSizing: "border-box" }}
        />
        {suggestions.length > 0 && (
          <ul
            aria-label="Mention suggestions"
            style={{ listStyle: "none", padding: 0, margin: "0.25rem 0 0", ...styles.row }}
          >
            {suggestions.map((agent) => (
              <li key={agent.id}>
                <button
                  type="button"
                  onClick={() => completeMention(agent)}
                  style={{ ...styles.button, fontSize: "0.8rem" }}
                >
                  @{handleFor(agent)}
                </button>
              </li>
            ))}
          </ul>
        )}
        <button
          type="submit"
          style={{ ...styles.button, marginTop: "0.5rem" }}
          disabled={busy || body.trim() === ""}
        >
          Post note
        </button>
      </form>
    </section>
  );
}
