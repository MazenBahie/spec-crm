import { useCallback, useEffect, useRef, useState } from "react";

import { listChatMessages, sendChatMessage, startChatSession } from "../../api/portalChat";
import { ErrorBanner, Loading, formatDateTime, styles, tokens } from "../../components/ui";
import type { ChatbotMessage } from "../../types/chatbot";

const OPTIMISTIC_PREFIX = "optimistic-";

export default function PortalChatPage() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatbotMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const session = await startChatSession();
      setSessionId(session.id);
      setMessages(await listChatMessages(session.id));
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    // jsdom (test environment) does not implement scrollIntoView.
    bottomRef.current?.scrollIntoView?.({ block: "nearest" });
  }, [messages]);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!sessionId || draft.trim() === "" || sending) return;

    const content = draft;
    const optimisticId = `${OPTIMISTIC_PREFIX}${crypto.randomUUID()}`;
    const optimisticMessage: ChatbotMessage = {
      id: optimisticId,
      session_id: sessionId,
      role: "user",
      content,
      created_at: new Date().toISOString(),
    };

    setMessages((current) => [...current, optimisticMessage]);
    setDraft("");
    setSending(true);
    setSendError(null);

    try {
      const turn = await sendChatMessage(sessionId, { content });
      setMessages((current) => [
        ...current.filter((m) => m.id !== optimisticId),
        turn.user_message,
        turn.assistant_message,
      ]);
    } catch (err) {
      // Roll back the optimistic message and keep the customer's typed text
      // recoverable -- nothing they typed is lost on failure.
      setMessages((current) => current.filter((m) => m.id !== optimisticId));
      setDraft(content);
      setSendError(err instanceof Error ? err.message : String(err));
    } finally {
      setSending(false);
    }
  }

  if (loading) {
    return (
      <main style={styles.page}>
        <Loading />
      </main>
    );
  }

  if (!sessionId) {
    return (
      <main style={styles.page}>
        <ErrorBanner message={loadError ?? "Could not start a chat session."} />
      </main>
    );
  }

  return (
    <main style={styles.page}>
      <h1 style={styles.h1}>Chat with us</h1>
      <p style={styles.muted}>Get quick answers powered by our AI assistant.</p>

      <ErrorBanner message={loadError} />

      <div
        style={{
          ...styles.card,
          minHeight: "16rem",
          maxHeight: "28rem",
          overflowY: "auto",
          display: "flex",
          flexDirection: "column",
          gap: "0.5rem",
        }}
      >
        {messages.length === 0 ? (
          <p style={styles.muted}>
            Ask a question and the assistant will look through our help center for you.
          </p>
        ) : (
          messages.map((message) => (
            <div
              key={message.id}
              style={{
                alignSelf: message.role === "user" ? "flex-end" : "flex-start",
                maxWidth: "80%",
              }}
            >
              {message.role === "assistant" && (
                <div
                  style={{
                    fontSize: "0.7rem",
                    textTransform: "uppercase",
                    letterSpacing: "0.05em",
                    color: tokens.accent,
                    marginBottom: "0.15rem",
                  }}
                >
                  AI Assistant
                </div>
              )}
              <div
                style={{
                  ...styles.card,
                  margin: 0,
                  background: message.role === "user" ? tokens.surface : "#fff",
                  border:
                    message.role === "assistant"
                      ? `1px solid ${tokens.accent}`
                      : `1px solid ${tokens.border}`,
                }}
              >
                <p style={{ margin: 0, whiteSpace: "pre-wrap" }}>{message.content}</p>
              </div>
              <p style={{ ...styles.muted, fontSize: "0.7rem", margin: "0.15rem 0 0" }}>
                {formatDateTime(message.created_at)}
              </p>
            </div>
          ))
        )}
        {sending && <p style={styles.muted}>Assistant is thinking…</p>}
        <div ref={bottomRef} />
      </div>

      <ErrorBanner message={sendError} />

      <form onSubmit={handleSubmit} style={{ ...styles.row, marginTop: "0.75rem" }}>
        <textarea
          aria-label="Your message"
          rows={2}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          style={{ ...styles.input, flex: 1 }}
        />
        <button type="submit" style={styles.button} disabled={sending || draft.trim() === ""}>
          {sending ? "Sending…" : "Send"}
        </button>
      </form>
    </main>
  );
}
