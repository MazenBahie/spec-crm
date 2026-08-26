import { useCallback, useEffect, useState, useSyncExternalStore } from "react";
import { Link } from "react-router-dom";

import { getActivity, getQueue, getRecentCustomers, getSummary } from "../api/dashboard";
import { getAgentId, setAgentId, subscribeAgentId } from "../api/agentContext";
import { listAgents } from "../api/tickets";
import ActivityFeedPanel from "../components/dashboard/ActivityFeedPanel";
import QuickRepliesPanel from "../components/dashboard/QuickRepliesPanel";
import TasksPanel from "../components/dashboard/TasksPanel";
import { ErrorBanner, Loading, formatDateTime, styles, tokens } from "../components/ui";
import type { ActivityEvent, DashboardSummary } from "../types/agent";
import type { Customer } from "../types/customer";
import type { Agent, Ticket } from "../types/ticket";

/** How often the summary strip and activity feed refresh themselves.
 * Short-polling on purpose — a WebSocket layer is a later story. */
const POLL_MS = 30_000;

function useAgentId(): string | null {
  return useSyncExternalStore(subscribeAgentId, getAgentId, () => null);
}

function SummaryTile({
  label,
  value,
  alert = false,
}: {
  label: string;
  value: number;
  alert?: boolean;
}) {
  return (
    <div style={{ ...styles.card, flex: "1 1 8rem", marginBottom: 0 }}>
      <div
        style={{
          fontSize: "1.6rem",
          fontWeight: 600,
          color: alert && value > 0 ? tokens.danger : "inherit",
        }}
      >
        {value}
      </div>
      <div style={{ color: tokens.muted, fontSize: "0.85rem" }}>{label}</div>
    </div>
  );
}

/**
 * Shown when no agent has been chosen, or when the stored one stopped being
 * valid (deleted, deactivated) and `client.request` cleared it on a 401.
 *
 * This is the placeholder for a sign-in screen and nothing more — picking an
 * agent here proves nothing, it only decides which `X-Agent-Id` goes on the
 * wire.
 */
function AgentPicker() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listAgents({ activeOnly: true })
      .then(setAgents)
      .catch((err: unknown) =>
        setError(err instanceof Error ? err.message : String(err)),
      );
  }, []);

  return (
    <main style={styles.page}>
      <h1 style={styles.h1}>Who is on shift?</h1>
      <p style={styles.muted}>
        Pick an agent to open their dashboard. Stands in for signing in, which is
        a later story.
      </p>

      <ErrorBanner message={error} />

      {agents.length === 0 && !error ? (
        <p style={styles.muted}>
          No active agents yet. Create one under{" "}
          <Link to="/tickets/setup">ticket setup</Link> first.
        </p>
      ) : (
        <div style={{ ...styles.row, marginTop: "1rem" }}>
          {agents.map((agent) => (
            <button
              key={agent.id}
              type="button"
              style={styles.button}
              onClick={() => setAgentId(agent.id)}
            >
              {agent.display_name}
            </button>
          ))}
        </div>
      )}
    </main>
  );
}

export default function DashboardPage() {
  const agentId = useAgentId();

  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [queue, setQueue] = useState<Ticket[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [events, setEvents] = useState<ActivityEvent[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  /** The whole screen, in one pass. Run on mount and after the agent changes.
   *
   * The agent roster is fetched here with the rest rather than in an effect of
   * its own: it is what turns ids in the activity feed into names, so it should
   * land with the feed, not after it. Its failure is swallowed — an unnamed
   * actor reads as "Someone", which beats an error banner over a working page.
   */
  const loadAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [nextSummary, nextQueue, nextCustomers, nextEvents, nextAgents] =
        await Promise.all([
          getSummary(),
          getQueue(),
          getRecentCustomers(),
          getActivity(),
          listAgents().catch(() => [] as Agent[]),
        ]);
      setSummary(nextSummary);
      setQueue(nextQueue);
      setCustomers(nextCustomers);
      setEvents(nextEvents);
      setAgents(nextAgents);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  /** Just the two live parts, for the poll. Silent on failure: a blip should
   * not replace a working screen with an error banner. */
  const refresh = useCallback(async () => {
    try {
      const [nextSummary, nextEvents] = await Promise.all([getSummary(), getActivity()]);
      setSummary(nextSummary);
      setEvents(nextEvents);
    } catch {
      // Keep whatever is on screen until the next tick.
    }
  }, []);

  useEffect(() => {
    if (!agentId) return;
    void loadAll();
  }, [agentId, loadAll]);

  useEffect(() => {
    if (!agentId) return undefined;
    const timer = window.setInterval(() => {
      // A backgrounded tab does not need fresh counts, and a wall of them
      // waking at once is a needless load spike.
      if (document.visibilityState !== "visible") return;
      void refresh();
    }, POLL_MS);
    return () => window.clearInterval(timer);
  }, [agentId, refresh]);

  if (!agentId) return <AgentPicker />;

  const agentName = agents.find((a) => a.id === agentId)?.display_name;

  return (
    <main style={styles.page}>
      <h1 style={styles.h1}>Dashboard</h1>
      <p style={styles.muted}>
        {agentName ? `Signed in as ${agentName}.` : "Your shift at a glance."}
      </p>

      <ErrorBanner message={error} />

      <div style={{ ...styles.row, marginTop: "1rem", alignItems: "stretch" }}>
        <SummaryTile label="Open assigned" value={summary?.open_assigned ?? 0} />
        <SummaryTile label="Overdue" value={summary?.overdue ?? 0} alert />
        <SummaryTile label="Tasks due today" value={summary?.tasks_due_today ?? 0} />
        <SummaryTile label="Unread mentions" value={summary?.unread_mentions ?? 0} />
      </div>

      <section aria-labelledby="queue-heading" style={{ marginTop: "2rem" }}>
        <h2 id="queue-heading" style={{ fontSize: "1.1rem" }}>
          My queue
        </h2>
        {loading && queue.length === 0 ? (
          <Loading />
        ) : queue.length === 0 ? (
          <p style={styles.muted}>You&rsquo;re all clear.</p>
        ) : (
          <table style={styles.table}>
            <thead>
              <tr>
                <th style={styles.th}>Reference</th>
                <th style={styles.th}>Subject</th>
                <th style={styles.th}>Priority</th>
                <th style={styles.th}>Due</th>
                <th style={styles.th}>Updated</th>
              </tr>
            </thead>
            <tbody>
              {queue.map((ticket) => (
                <tr key={ticket.id}>
                  <td style={styles.td}>
                    <Link to={`/tickets/${ticket.id}`}>{ticket.reference}</Link>
                  </td>
                  <td style={styles.td}>{ticket.subject}</td>
                  <td style={styles.td}>{ticket.priority}</td>
                  <td style={{ ...styles.td, color: ticket.is_overdue ? tokens.danger : "inherit" }}>
                    {formatDateTime(ticket.due_at)}
                    {ticket.is_overdue && " (overdue)"}
                  </td>
                  <td style={styles.td}>{formatDateTime(ticket.updated_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section aria-labelledby="recent-customers-heading" style={{ marginTop: "2rem" }}>
        <h2 id="recent-customers-heading" style={{ fontSize: "1.1rem" }}>
          Recent customers
        </h2>
        {loading && customers.length === 0 ? (
          <Loading />
        ) : customers.length === 0 ? (
          <p style={styles.muted}>Nobody yet — customers you work with will show up here.</p>
        ) : (
          <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {customers.map((customer) => (
              <li key={customer.id} style={styles.card}>
                <Link to={`/customers/${customer.id}`}>{customer.display_name}</Link>
                {customer.company && (
                  <span style={{ color: tokens.muted }}> · {customer.company}</span>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      <div style={{ marginTop: "2rem" }}>
        <TasksPanel />
      </div>

      <div style={{ marginTop: "2rem" }}>
        <QuickRepliesPanel />
      </div>

      <div style={{ marginTop: "2rem" }}>
        <ActivityFeedPanel events={events} agents={agents} loading={loading} />
      </div>
    </main>
  );
}
