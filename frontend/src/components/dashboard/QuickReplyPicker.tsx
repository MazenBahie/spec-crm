import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { list as listQuickReplies } from "../../api/quickReplies";
import type { QuickReply } from "../../types/agent";
import { styles, tokens } from "../ui";

/** What a `{{token}}` can be resolved against. Every field is optional — the
 * picker is used from places that do not have a customer or agent loaded. */
export interface TemplateContext {
  customer?: { display_name?: string | null } | null;
  ticket?: { id?: string; reference?: string; subject?: string } | null;
  agent?: { display_name?: string | null } | null;
}

const TOKEN_PATTERN = /\{\{\s*([\w.]+)\s*\}\}/g;

/** "Dana Support" → "Dana". A crude split, but display_name is all we store. */
function firstName(displayName: string | null | undefined): string | undefined {
  const trimmed = displayName?.trim();
  return trimmed ? trimmed.split(/\s+/)[0] : undefined;
}

function lookup(token: string, context: TemplateContext): string | undefined {
  switch (token) {
    case "customer.first_name":
      return firstName(context.customer?.display_name);
    case "customer.display_name":
      return context.customer?.display_name ?? undefined;
    case "ticket.id":
      return context.ticket?.id;
    case "ticket.reference":
      return context.ticket?.reference;
    case "ticket.subject":
      return context.ticket?.subject;
    case "agent.display_name":
      return context.agent?.display_name ?? undefined;
    default:
      return undefined;
  }
}

/**
 * Expand `{{token}}`s against the loaded ticket/customer/agent.
 *
 * An unknown token — or a known one with nothing behind it — is left as
 * literal text rather than replaced with an empty string: a visible
 * `{{customer.first_name}}` in the composer is a mistake the agent can catch
 * before sending, where a silent blank is not.
 */
export function renderTemplate(body: string, context: TemplateContext): string {
  return body.replace(TOKEN_PATTERN, (literal, token: string) => {
    const value = lookup(token, context);
    if (value === undefined) {
      if (import.meta.env?.DEV) {
        console.warn(`quick reply: no value for token {{${token}}}`);
      }
      return literal;
    }
    return value;
  });
}

interface Props {
  /** The composer to insert into. Insertion happens at the caret. */
  textareaRef: React.RefObject<HTMLTextAreaElement | null>;
  value: string;
  onChange: (next: string) => void;
  context?: TemplateContext;
}

export default function QuickReplyPicker({
  textareaRef,
  value,
  onChange,
  context = {},
}: Props) {
  const [replies, setReplies] = useState<QuickReply[]>([]);
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    // Failure is silent by design: a broken or unauthenticated quick-reply
    // library must not stop an agent replying to a customer. The shape check
    // covers the same ground — an unexpected body leaves an empty picker
    // rather than taking the composer down with it.
    listQuickReplies()
      .then((loaded) => setReplies(Array.isArray(loaded) ? loaded : []))
      .catch(() => setReplies([]));
  }, []);

  const show = useCallback(() => {
    setOpen(true);
    setSearch("");
  }, []);

  // Ctrl+/ opens the picker from inside the composer.
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (!event.ctrlKey || event.key !== "/") return;
      const target = event.target as Node | null;
      const insideComposer =
        target === textareaRef.current || target === searchRef.current;
      if (!insideComposer) return;
      event.preventDefault();
      show();
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [show, textareaRef]);

  // Focus the search box once the dropdown has rendered.
  useEffect(() => {
    if (open) searchRef.current?.focus();
  }, [open]);

  const matches = useMemo(() => {
    const needle = search.trim().toLowerCase();
    if (!needle) return replies;
    return replies.filter(
      (reply) =>
        reply.title.toLowerCase().includes(needle) ||
        (reply.shortcut ?? "").toLowerCase().includes(needle),
    );
  }, [replies, search]);

  function insert(reply: QuickReply) {
    const rendered = renderTemplate(reply.body, context);
    const textarea = textareaRef.current;
    // Caret position when the composer is mounted; append otherwise.
    const start = textarea?.selectionStart ?? value.length;
    const end = textarea?.selectionEnd ?? value.length;
    const next = value.slice(0, start) + rendered + value.slice(end);

    onChange(next);
    setOpen(false);

    // After React has written the new value, put the caret just past what was
    // inserted so the agent can keep typing where they left off.
    requestAnimationFrame(() => {
      if (!textarea) return;
      const caret = start + rendered.length;
      textarea.focus();
      textarea.setSelectionRange(caret, caret);
    });
  }

  return (
    <div style={{ position: "relative" }}>
      <button
        type="button"
        onClick={() => (open ? setOpen(false) : show())}
        aria-expanded={open}
        aria-haspopup="listbox"
        style={{ ...styles.button, fontSize: "0.85rem" }}
      >
        Quick reply <span style={{ color: tokens.muted }}>(Ctrl+/)</span>
      </button>

      {open && (
        <div
          style={{
            position: "absolute",
            zIndex: 10,
            marginTop: "0.25rem",
            minWidth: "18rem",
            background: "#fff",
            border: `1px solid ${tokens.border}`,
            borderRadius: 6,
            padding: "0.5rem",
            boxShadow: "0 4px 12px rgba(0,0,0,0.08)",
          }}
        >
          <input
            ref={searchRef}
            aria-label="Search quick replies"
            placeholder="Search…"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Escape") setOpen(false);
            }}
            style={{ ...styles.input, width: "100%", boxSizing: "border-box" }}
          />
          {matches.length === 0 ? (
            <p style={{ ...styles.muted, margin: "0.5rem 0 0", fontSize: "0.9rem" }}>
              {replies.length === 0
                ? "No quick replies yet. Add some from the dashboard."
                : "Nothing matches that."}
            </p>
          ) : (
            <ul role="listbox" style={{ listStyle: "none", margin: "0.5rem 0 0", padding: 0 }}>
              {matches.map((reply) => (
                <li key={reply.id}>
                  <button
                    type="button"
                    role="option"
                    aria-selected={false}
                    onClick={() => insert(reply)}
                    style={{
                      ...styles.button,
                      display: "block",
                      width: "100%",
                      textAlign: "left",
                      border: "none",
                      padding: "0.35rem 0.4rem",
                    }}
                  >
                    <strong style={{ fontSize: "0.9rem" }}>{reply.title}</strong>
                    {reply.shortcut && (
                      <span style={{ color: tokens.muted, fontSize: "0.8rem" }}>
                        {" "}
                        /{reply.shortcut}
                      </span>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
