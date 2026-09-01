import { useCallback, useEffect, useRef, useState } from "react";

import { suggestReply } from "../../api/ai";
import { listChannels, listTicketMessages, sendTicketMessage } from "../../api/channels";
import QuickReplyPicker from "../dashboard/QuickReplyPicker";
import type { Channel, ChannelMessage, ChannelSlug, MessageStatus } from "../../types/channel";
import type { TicketDetail } from "../../types/ticket";
import { ErrorBanner, Loading, formatDateTime, styles, tokens } from "../ui";

interface Props {
  ticketId: string;
  /** Supplies `{{ticket.*}}` and `{{customer.*}}` values to the quick-reply
   * picker. Optional — without it those tokens stay literal rather than the
   * composer disappearing. */
  ticket?: TicketDetail | null;
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

export default function MessagesPanel({ ticketId, ticket = null }: Props) {
  const [messages, setMessages] = useState<ChannelMessage[]>([]);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [slug, setSlug] = useState<ChannelSlug | "">("");
  const [body, setBody] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [suggesting, setSuggesting] = useState(false);
  const [suggestionActive, setSuggestionActive] = useState(false);
  const bodyRef = useRef<HTMLTextAreaElement>(null);

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

  function updateBody(next: string) {
    setBody(next);
    setSuggestionActive(false);
  }

  const hasInboundMessage = messages.some((message) => message.direction === "inbound");

  async function handleSuggestReply() {
    if (body.trim() !== "") {
      const proceed = window.confirm(
        "Replace your draft with an AI-suggested reply? Your current draft will be lost.",
      );
      if (!proceed) return;
    }
    setSuggesting(true);
    setError(null);
    try {
      const draft = await suggestReply(ticketId);
      setBody(draft);
      setSuggestionActive(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSuggesting(false);
    }
  }

  async function handleSend(event: React.FormEvent) {
    event.preventDefault();
    if (!slug) return;
    setBusy(true);
    setError(null);
    try {
      const sent = await sendTicketMessage(ticketId, { channel_slug: slug, body });
      setBody("");
      setSuggestionActive(false);
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
        <div style={{ ...styles.row, marginTop: "0.5rem" }}>
          <QuickReplyPicker
            textareaRef={bodyRef}
            value={body}
            onChange={updateBody}
            context={{ ticket: ticket ?? undefined, customer: ticket?.customer }}
          />
          <button
            type="button"
            onClick={() => void handleSuggestReply()}
            disabled={!hasInboundMessage || suggesting || busy}
            title={
              hasInboundMessage
                ? undefined
                : "Nothing from the customer yet to draft a reply to"
            }
            style={{ ...styles.button, fontSize: "0.85rem" }}
          >
            {suggesting ? "Suggesting…" : "Suggest a reply"}
          </button>
        </div>
        {suggestionActive && (
          <p
            role="status"
            style={{ ...styles.muted, margin: "0.35rem 0 0", fontSize: "0.8rem" }}
          >
            AI-drafted suggestion — review and edit before sending.
          </p>
        )}
        <textarea
          ref={bodyRef}
          aria-label="Message body"
          placeholder="Write a reply…"
          rows={3}
          value={body}
          onChange={(event) => updateBody(event.target.value)}
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
