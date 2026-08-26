import { useCallback, useEffect, useState } from "react";

import { listChannels, listTicketMessages, sendTicketMessage } from "../../api/channels";
import type { Channel, ChannelMessage, ChannelSlug, MessageStatus } from "../../types/channel";
import { ErrorBanner, Loading, formatDateTime, styles, tokens } from "../ui";

interface Props {
  ticketId: string;
}

/** `failed` is the expected outcome until an adapter story lands, so it reads
 * as a plain red state rather than an exception. */
function StatusPill({ status }: { status: MessageStatus }) {
  const failed = status === "failed";
  const settled = status === "delivered" || status === "received";
  const color = failed ? tokens.danger : settled ? tokens.accent : tokens.muted;
  return (
    <span
      style={{
        fontSize: "0.75rem",
        textTransform: "uppercase",
        letterSpacing: "0.05em",
        padding: "0.15rem 0.45rem",
        borderRadius: 10,
        border: `1px solid ${color}`,
        color,
      }}
    >
      {status}
    </span>
  );
}

export default function MessagesPanel({ ticketId }: Props) {
  const [messages, setMessages] = useState<ChannelMessage[]>([]);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [slug, setSlug] = useState<ChannelSlug | "">("");
  const [body, setBody] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [page, catalogue] = await Promise.all([
        listTicketMessages(ticketId, { limit: 200 }),
        listChannels(),
      ]);
      setMessages(page.items);
      setChannels(catalogue);
      // Default to the ticket's primary channel — the one the customer used
      // first, i.e. the oldest message in the thread — and fall back to the
      // first enabled channel on a thread with no messages yet. An explicit
      // choice already made by the agent survives the refresh after a send.
      setSlug(
        (current) =>
          current ||
          page.items[0]?.channel_slug ||
          catalogue.find((channel) => channel.is_enabled)?.slug ||
          "",
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [ticketId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleSend(event: React.FormEvent) {
    event.preventDefault();
    if (!slug) return;
    setBusy(true);
    setError(null);
    try {
      const sent = await sendTicketMessage(ticketId, { channel_slug: slug, body });
      setBody("");
      await load();
      // A failed send is a 201, not a rejected promise: the row exists and
      // carries the reason. Surface it next to the composer as well as in the
      // thread, so it is not missed after the list re-renders. Reported after
      // the refresh, because `load` clears the banner on the way in.
      if (sent.status === "failed") {
        setError(sent.error_reason ?? `Delivery on ${sent.channel_slug} failed.`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  const labelFor = (messageSlug: ChannelSlug): string =>
    channels.find((channel) => channel.slug === messageSlug)?.display_name ?? messageSlug;

  return (
    <section>
      <h2 style={{ fontSize: "1.1rem" }}>Messages</h2>
      <ErrorBanner message={error} />

      {loading ? (
        <Loading />
      ) : messages.length === 0 ? (
        <p style={styles.muted}>No messages on this ticket yet.</p>
      ) : (
        <ol style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {messages.map((message) => (
            <li key={message.id} style={styles.card}>
              <div style={{ ...styles.row, justifyContent: "space-between" }}>
                <span style={styles.row}>
                  <strong>{message.direction === "inbound" ? "Inbound" : "Outbound"}</strong>
                  <span style={styles.muted}>{labelFor(message.channel_slug)}</span>
                  <StatusPill status={message.status} />
                </span>
                <span style={styles.muted}>{formatDateTime(message.created_at)}</span>
              </div>
              <p style={{ whiteSpace: "pre-wrap", margin: "0.5rem 0 0" }}>{message.body}</p>
              {message.error_reason && (
                <p style={{ color: tokens.danger, margin: "0.25rem 0 0", fontSize: "0.85rem" }}>
                  {message.error_reason}
                </p>
              )}
            </li>
          ))}
        </ol>
      )}

      <form onSubmit={handleSend} style={{ ...styles.card, marginTop: "1rem" }}>
        <h3 style={{ fontSize: "0.95rem", marginTop: 0 }}>Reply</h3>
        <label htmlFor="message-channel" style={styles.label}>
          Channel
        </label>
        <select
          id="message-channel"
          aria-label="Channel"
          value={slug}
          disabled={busy}
          onChange={(event) => setSlug(event.target.value as ChannelSlug)}
          style={styles.input}
        >
          {channels.map((channel) => (
            <option key={channel.slug} value={channel.slug} disabled={!channel.is_enabled}>
              {channel.display_name}
              {channel.is_enabled ? "" : " (disabled)"}
            </option>
          ))}
        </select>
        <textarea
          aria-label="Message body"
          placeholder="Write a reply…"
          rows={3}
          value={body}
          onChange={(event) => setBody(event.target.value)}
          style={{ ...styles.input, width: "100%", marginTop: "0.5rem" }}
        />
        <button
          type="submit"
          style={{ ...styles.button, marginTop: "0.5rem" }}
          disabled={busy || !slug || body.trim() === ""}
        >
          Send
        </button>
      </form>
    </section>
  );
}
