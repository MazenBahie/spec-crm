import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import {
  createAgent,
  createCategory,
  deactivateAgent,
  listAgents,
  listCategories,
  updateAgent,
  updateCategory,
} from "../api/tickets";
import { ErrorBanner, Loading, styles } from "../components/ui";
import type { Agent, TicketCategory, TicketPriority } from "../types/ticket";
import { TICKET_PRIORITIES } from "../types/ticket";

export default function TicketSetupPage() {
  const [categories, setCategories] = useState<TicketCategory[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [categoryName, setCategoryName] = useState("");
  const [categoryPriority, setCategoryPriority] = useState<TicketPriority>("normal");
  const [agentName, setAgentName] = useState("");
  const [agentEmail, setAgentEmail] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [categoryRows, agentRows] = await Promise.all([listCategories(), listAgents()]);
      setCategories(categoryRows);
      setAgents(agentRows);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleAddCategory(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await createCategory({ name: categoryName.trim(), default_priority: categoryPriority });
      setCategoryName("");
      setCategoryPriority("normal");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function toggleCategoryActive(category: TicketCategory) {
    setBusy(true);
    setError(null);
    try {
      await updateCategory(category.id, { is_active: !category.is_active });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleAddAgent(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await createAgent({ display_name: agentName.trim(), email: agentEmail.trim() || null });
      setAgentName("");
      setAgentEmail("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function toggleAgentActive(agent: Agent) {
    setBusy(true);
    setError(null);
    try {
      if (agent.is_active) {
        await deactivateAgent(agent.id);
      } else {
        await updateAgent(agent.id, { is_active: true });
      }
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return (
      <main style={styles.page}>
        <Loading />
      </main>
    );
  }

  return (
    <main style={styles.page}>
      <p style={styles.muted}>
        <Link to="/tickets">← Tickets</Link>
      </p>
      <h1 style={styles.h1}>Ticket setup</h1>
      <p style={styles.muted}>Manage the categories and agents used to route tickets.</p>

      <ErrorBanner message={error} />

      <section>
        <h2 style={{ fontSize: "1.1rem" }}>Categories</h2>
        {categories.length === 0 ? (
          <p style={styles.muted}>No categories yet.</p>
        ) : (
          <table style={styles.table}>
            <thead>
              <tr>
                <th style={styles.th}>Name</th>
                <th style={styles.th}>Default priority</th>
                <th style={styles.th}>Active</th>
                <th style={styles.th} />
              </tr>
            </thead>
            <tbody>
              {categories.map((category) => (
                <tr key={category.id}>
                  <td style={styles.td}>{category.name}</td>
                  <td style={styles.td}>{category.default_priority}</td>
                  <td style={styles.td}>{category.is_active ? "Yes" : "No"}</td>
                  <td style={styles.td}>
                    <button
                      type="button"
                      style={styles.button}
                      disabled={busy}
                      onClick={() => void toggleCategoryActive(category)}
                    >
                      {category.is_active ? "Deactivate" : "Activate"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        <form onSubmit={handleAddCategory} style={{ ...styles.card, marginTop: "1rem" }}>
          <h3 style={{ fontSize: "0.95rem", marginTop: 0 }}>Add category</h3>
          <div style={styles.row}>
            <input
              aria-label="Category name"
              placeholder="Name"
              required
              value={categoryName}
              onChange={(event) => setCategoryName(event.target.value)}
              style={{ ...styles.input, flex: "1 1 12rem" }}
            />
            <select
              aria-label="Default priority"
              value={categoryPriority}
              onChange={(event) => setCategoryPriority(event.target.value as TicketPriority)}
              style={styles.input}
            >
              {TICKET_PRIORITIES.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
            <button type="submit" style={styles.button} disabled={busy || categoryName.trim() === ""}>
              Add
            </button>
          </div>
        </form>
      </section>

      <section style={{ marginTop: "2rem" }}>
        <h2 style={{ fontSize: "1.1rem" }}>Agents</h2>
        {agents.length === 0 ? (
          <p style={styles.muted}>No agents yet.</p>
        ) : (
          <table style={styles.table}>
            <thead>
              <tr>
                <th style={styles.th}>Name</th>
                <th style={styles.th}>Email</th>
                <th style={styles.th}>Active</th>
                <th style={styles.th} />
              </tr>
            </thead>
            <tbody>
              {agents.map((agent) => (
                <tr key={agent.id}>
                  <td style={styles.td}>{agent.display_name}</td>
                  <td style={styles.td}>{agent.email ?? "—"}</td>
                  <td style={styles.td}>{agent.is_active ? "Yes" : "No"}</td>
                  <td style={styles.td}>
                    <button
                      type="button"
                      style={styles.button}
                      disabled={busy}
                      onClick={() => void toggleAgentActive(agent)}
                    >
                      {agent.is_active ? "Deactivate" : "Reactivate"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        <form onSubmit={handleAddAgent} style={{ ...styles.card, marginTop: "1rem" }}>
          <h3 style={{ fontSize: "0.95rem", marginTop: 0 }}>Add agent</h3>
          <div style={styles.row}>
            <input
              aria-label="Agent name"
              placeholder="Name"
              required
              value={agentName}
              onChange={(event) => setAgentName(event.target.value)}
              style={{ ...styles.input, flex: "1 1 12rem" }}
            />
            <input
              aria-label="Agent email"
              placeholder="Email"
              value={agentEmail}
              onChange={(event) => setAgentEmail(event.target.value)}
              style={styles.input}
            />
            <button type="submit" style={styles.button} disabled={busy || agentName.trim() === ""}>
              Add
            </button>
          </div>
        </form>
      </section>
    </main>
  );
}
