import { useEffect, useState } from "react";

import { assignTicket, changeTicketStatus, escalateTicket, listAgents } from "../../api/tickets";
import { ErrorBanner, styles } from "../ui";
import type { Agent, Ticket, TicketStatus } from "../../types/ticket";
import { ALLOWED_TRANSITIONS, MAX_ESCALATION_LEVEL } from "../../types/ticket";

interface Props {
  ticket: Ticket;
  onChanged: () => void;
}

function isTerminal(status: TicketStatus): boolean {
  return status === "resolved" || status === "closed";
}

export default function TicketWorkflowPanel({ ticket, onChanged }: Props) {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [comment, setComment] = useState("");

  useEffect(() => {
    listAgents().then(setAgents).catch(() => setAgents([]));
  }, []);

  const nextStatuses = ALLOWED_TRANSITIONS[ticket.status] ?? [];
  const terminal = isTerminal(ticket.status);

  async function handleStatusChange(target: TicketStatus) {
    setBusy(true);
    setError(null);
    try {
      // The <select> only ever offers a status from ALLOWED_TRANSITIONS, but
      // the server is still the source of truth — a stale client can send an
      // option that is no longer legal, and that surfaces here as a 409.
      await changeTicketStatus(ticket.id, target, { comment: comment.trim() || undefined });
      setComment("");
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleAssign(assigneeId: string) {
    setBusy(true);
    setError(null);
    try {
      await assignTicket(ticket.id, assigneeId || null);
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleEscalate() {
    setBusy(true);
    setError(null);
    try {
      await escalateTicket(ticket.id, { comment: comment.trim() || undefined });
      setComment("");
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  const escalateDisabled = busy || terminal || ticket.escalation_level >= MAX_ESCALATION_LEVEL;

  return (
    <section>
      <h2 style={{ fontSize: "1.1rem" }}>Workflow</h2>
      <ErrorBanner message={error} />

      <div style={{ marginBottom: "1rem" }}>
        <label htmlFor="workflow-status" style={styles.label}>
          Move to status
        </label>
        <div style={styles.row}>
          <select
            id="workflow-status"
            aria-label="Move to status"
            disabled={busy || nextStatuses.length === 0}
            defaultValue=""
            onChange={(event) => {
              const target = event.target.value as TicketStatus;
              event.target.value = "";
              if (target) void handleStatusChange(target);
            }}
            style={styles.input}
          >
            <option value="" disabled>
              {nextStatuses.length === 0 ? "No further transitions" : "Choose a status…"}
            </option>
            {nextStatuses.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div style={{ marginBottom: "1rem" }}>
        <label htmlFor="workflow-assignee" style={styles.label}>
          Assignee
        </label>
        <select
          id="workflow-assignee"
          aria-label="Assignee"
          value={ticket.assignee_id ?? ""}
          disabled={busy || terminal}
          onChange={(event) => void handleAssign(event.target.value)}
          style={styles.input}
        >
          <option value="">— Unassigned —</option>
          {agents.map((agent) => (
            <option key={agent.id} value={agent.id}>
              {agent.display_name}
              {agent.is_active ? "" : " (inactive)"}
            </option>
          ))}
        </select>
      </div>

      <div style={{ marginBottom: "1rem" }}>
        <label htmlFor="workflow-comment" style={styles.label}>
          Comment (attached to the next status change or escalation)
        </label>
        <textarea
          id="workflow-comment"
          rows={2}
          value={comment}
          onChange={(event) => setComment(event.target.value)}
          style={{ ...styles.input, width: "100%" }}
        />
      </div>

      <button
        type="button"
        style={styles.button}
        disabled={escalateDisabled}
        onClick={() => void handleEscalate()}
      >
        Escalate (level {ticket.escalation_level} / {MAX_ESCALATION_LEVEL})
      </button>
    </section>
  );
}
