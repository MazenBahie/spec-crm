import { Link } from "react-router-dom";

import type { ActivityEvent } from "../../types/agent";
import type { Agent } from "../../types/ticket";
import { Loading, formatDateTime, styles, tokens } from "../ui";

interface Props {
  events: ActivityEvent[];
  agents: Agent[];
  loading?: boolean;
}

function payloadText(event: ActivityEvent, key: string): string | undefined {
  const value = event.payload?.[key];
  return typeof value === "string" ? value : undefined;
}

/** One line of plain English per event type.
 *
 * `agentName` resolves ids against the loaded roster; an event recorded with no
 * actor (an unauthenticated caller changed the ticket) reads as "Someone",
 * which is honest — the backend genuinely does not know who it was.
 */
function describe(event: ActivityEvent, agentName: (id: string | null) => string): string {
  const who = agentName(event.agent_id);
  const ref = payloadText(event, "reference") ?? "a ticket";

  switch (event.event_type) {
    case "ticket.assigned": {
      const to = payloadText(event, "to");
      return to
        ? `${who} assigned ${ref} to ${agentName(to)}`
        : `${who} unassigned ${ref}`;
    }
    case "ticket.status_changed":
      return `${who} moved ${ref} from ${payloadText(event, "from") ?? "?"} to ${
        payloadText(event, "to") ?? "?"
      }`;
    case "ticket.replied": {
      const channel = payloadText(event, "channel") ?? "a channel";
      const status = payloadText(event, "status");
      const outcome = status === "failed" ? " — delivery failed" : "";
      return `${who} replied on ${ref} via ${channel}${outcome}`;
    }
    case "note.added":
      return `${who} added an internal note on ${ref}`;
    case "mention":
      return `${who} mentioned you on ${ref}`;
    default:
      return `${who} touched ${ref}`;
  }
}

export default function ActivityFeedPanel({ events, agents, loading = false }: Props) {
  const agentName = (id: string | null): string => {
    if (!id) return "Someone";
    return agents.find((a) => a.id === id)?.display_name ?? "Someone";
  };

  return (
    <section aria-labelledby="activity-heading">
      <h2 id="activity-heading" style={{ fontSize: "1.1rem" }}>
        Team activity
      </h2>

      {loading && events.length === 0 ? (
        <Loading />
      ) : events.length === 0 ? (
        <p style={styles.muted}>Nothing has happened on your tickets yet.</p>
      ) : (
        <ol style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {events.map((event) => (
            <li
              key={event.id}
              style={{
                borderLeft: `2px solid ${tokens.border}`,
                padding: "0.35rem 0 0.35rem 0.75rem",
                marginBottom: "0.35rem",
              }}
            >
              <div>
                {describe(event, agentName)}
                {event.ticket_id && (
                  <>
                    {" "}
                    <Link to={`/tickets/${event.ticket_id}`}>open</Link>
                  </>
                )}
              </div>
              <span style={{ color: tokens.muted, fontSize: "0.8rem" }}>
                {formatDateTime(event.created_at)}
              </span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
