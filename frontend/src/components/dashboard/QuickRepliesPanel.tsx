import { useCallback, useEffect, useState } from "react";

import { create, list, remove, update } from "../../api/quickReplies";
import type { QuickReply, QuickReplyScope } from "../../types/agent";
import { QUICK_REPLY_SCOPES } from "../../types/agent";
import { ErrorBanner, Loading, styles, tokens } from "../ui";

function ScopeBadge({ scope }: { scope: QuickReplyScope }) {
  const team = scope === "team";
  return (
    <span
      style={{
        fontSize: "0.75rem",
        textTransform: "uppercase",
        letterSpacing: "0.05em",
        padding: "0.15rem 0.45rem",
        borderRadius: 10,
        border: `1px solid ${team ? tokens.accent : tokens.muted}`,
        color: team ? tokens.accent : tokens.muted,
      }}
    >
      {scope}
    </span>
  );
}

interface DraftProps {
  initial?: QuickReply;
  submitLabel: string;
  onSubmit: (draft: {
    scope: QuickReplyScope;
    title: string;
    body: string;
    shortcut: string | null;
  }) => Promise<void>;
  onCancel?: () => void;
}

/** The add and edit forms are the same shape, so they are the same component. */
function QuickReplyForm({ initial, submitLabel, onSubmit, onCancel }: DraftProps) {
  const [scope, setScope] = useState<QuickReplyScope>(initial?.scope ?? "personal");
  const [title, setTitle] = useState(initial?.title ?? "");
  const [body, setBody] = useState(initial?.body ?? "");
  const [shortcut, setShortcut] = useState(initial?.shortcut ?? "");
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      await onSubmit({
        scope,
        title: title.trim(),
        body,
        shortcut: shortcut.trim() || null,
      });
      if (!initial) {
        setTitle("");
        setBody("");
        setShortcut("");
      }
    } finally {
      setBusy(false);
    }
  }

  const id = initial ? `edit-${initial.id}` : "new";

  return (
    <form onSubmit={handleSubmit} style={styles.card}>
      <div style={styles.row}>
        <input
          aria-label={initial ? "Edit title" : "Quick reply title"}
          placeholder="Title"
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          style={{ ...styles.input, flex: "1 1 10rem" }}
        />
        <input
          aria-label={initial ? "Edit shortcut" : "Quick reply shortcut"}
          placeholder="shortcut"
          value={shortcut}
          onChange={(event) => setShortcut(event.target.value)}
          style={{ ...styles.input, width: "8rem" }}
        />
        <select
          aria-label={initial ? "Edit scope" : "Quick reply scope"}
          value={scope}
          onChange={(event) => setScope(event.target.value as QuickReplyScope)}
          style={styles.input}
        >
          {QUICK_REPLY_SCOPES.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      </div>
      <textarea
        aria-label={initial ? "Edit body" : "Quick reply body"}
        placeholder="Hi {{customer.first_name}}, about {{ticket.reference}}…"
        rows={3}
        value={body}
        onChange={(event) => setBody(event.target.value)}
        style={{ ...styles.input, width: "100%", boxSizing: "border-box", marginTop: "0.5rem" }}
      />
      <p style={{ ...styles.muted, fontSize: "0.8rem", margin: "0.25rem 0 0" }}>
        Tokens available: {"{{customer.first_name}}"}, {"{{ticket.reference}}"},{" "}
        {"{{agent.display_name}}"}. They are expanded when the reply is inserted.
      </p>
      <div style={{ ...styles.row, marginTop: "0.5rem" }}>
        <button
          type="submit"
          id={id}
          style={styles.button}
          disabled={busy || title.trim() === "" || body.trim() === ""}
        >
          {submitLabel}
        </button>
        {onCancel && (
          <button type="button" style={styles.button} onClick={onCancel} disabled={busy}>
            Cancel
          </button>
        )}
      </div>
    </form>
  );
}

export default function QuickRepliesPanel() {
  const [replies, setReplies] = useState<QuickReply[]>([]);
  const [editing, setEditing] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setReplies(await list());
    } catch (err) {
      setReplies([]);
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function guard(action: () => Promise<void>) {
    setError(null);
    try {
      await action();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function handleDelete(reply: QuickReply) {
    if (!window.confirm(`Delete the quick reply "${reply.title}"?`)) return;
    await guard(async () => {
      await remove(reply.id);
      setReplies((current) => current.filter((r) => r.id !== reply.id));
    });
  }

  return (
    <section aria-labelledby="quick-replies-heading">
      <h2 id="quick-replies-heading" style={{ fontSize: "1.1rem" }}>
        Quick replies
      </h2>

      <ErrorBanner message={error} />

      <QuickReplyForm
        submitLabel="Add quick reply"
        onSubmit={(draft) =>
          guard(async () => {
            // Scope decides ownership on the server; `owner_agent_id` is never
            // sent, which is what keeps the personal/team invariant safe.
            const created = await create(draft);
            setReplies((current) => [created, ...current]);
          })
        }
      />

      {loading ? (
        <Loading />
      ) : replies.length === 0 ? (
        <p style={styles.muted}>No quick replies yet — the one above will be the first.</p>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {replies.map((reply) =>
            editing === reply.id ? (
              <li key={reply.id}>
                <QuickReplyForm
                  initial={reply}
                  submitLabel="Save"
                  onCancel={() => setEditing(null)}
                  onSubmit={(draft) =>
                    guard(async () => {
                      const saved = await update(reply.id, draft);
                      setReplies((current) =>
                        current.map((r) => (r.id === saved.id ? saved : r)),
                      );
                      setEditing(null);
                    })
                  }
                />
              </li>
            ) : (
              <li key={reply.id} style={styles.card}>
                <div style={{ ...styles.row, justifyContent: "space-between" }}>
                  <span style={styles.row}>
                    <strong>{reply.title}</strong>
                    <ScopeBadge scope={reply.scope} />
                    {reply.shortcut && (
                      <span style={{ color: tokens.muted, fontSize: "0.85rem" }}>
                        /{reply.shortcut}
                      </span>
                    )}
                  </span>
                  <span style={styles.row}>
                    <button
                      type="button"
                      aria-label={`Edit ${reply.title}`}
                      onClick={() => setEditing(reply.id)}
                      style={{ ...styles.button, fontSize: "0.8rem" }}
                    >
                      Edit
                    </button>
                    <button
                      type="button"
                      aria-label={`Delete ${reply.title}`}
                      onClick={() => void handleDelete(reply)}
                      style={{ ...styles.button, fontSize: "0.8rem", color: tokens.danger }}
                    >
                      Delete
                    </button>
                  </span>
                </div>
                <p
                  style={{
                    whiteSpace: "pre-wrap",
                    margin: "0.5rem 0 0",
                    color: tokens.muted,
                    fontSize: "0.9rem",
                  }}
                >
                  {reply.body}
                </p>
              </li>
            ),
          )}
        </ul>
      )}
    </section>
  );
}
