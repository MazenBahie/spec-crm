import { useCallback, useEffect, useMemo, useState } from "react";

import {
  completeTask,
  createTask,
  deleteTask,
  listTasks,
  reopenTask,
} from "../../api/tasks";
import type { AgentTask } from "../../types/agent";
import { ErrorBanner, Loading, formatDateTime, styles, tokens } from "../ui";

type Filter = "open" | "today" | "all";

const FILTERS: Array<{ key: Filter; label: string }> = [
  { key: "open", label: "Open" },
  { key: "today", label: "Due today" },
  { key: "all", label: "All" },
];

/** True when `iso` falls inside the viewer's local calendar day.
 *
 * Local, unlike the backend's `tasks_due_today` count, which has no idea what
 * zone the agent is in and uses UTC. The two can disagree either side of
 * midnight — a known gap until agents carry a timezone.
 */
function isDueToday(iso: string | null): boolean {
  if (!iso) return false;
  const when = new Date(iso);
  if (Number.isNaN(when.getTime())) return false;
  const now = new Date();
  return (
    when.getFullYear() === now.getFullYear() &&
    when.getMonth() === now.getMonth() &&
    when.getDate() === now.getDate()
  );
}

export default function TasksPanel() {
  const [tasks, setTasks] = useState<AgentTask[]>([]);
  const [filter, setFilter] = useState<Filter>("open");
  const [title, setTitle] = useState("");
  const [remindAt, setRemindAt] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // Always fetched whole: the list is one agent's to-dos, and filtering
      // client-side keeps the chips instant.
      setTasks(await listTasks());
    } catch (err) {
      setTasks([]);
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const visible = useMemo(() => {
    if (filter === "all") return tasks;
    if (filter === "open") return tasks.filter((t) => t.status === "open");
    return tasks.filter((t) => t.status === "open" && isDueToday(t.remind_at));
  }, [tasks, filter]);

  async function handleAdd(event: React.FormEvent) {
    event.preventDefault();
    if (title.trim() === "") return;
    setBusy(true);
    setError(null);
    try {
      const created = await createTask({
        title: title.trim(),
        // `datetime-local` has no zone; the browser reads it as local time,
        // which is what the agent meant, and it goes to the wire as UTC.
        remind_at: remindAt ? new Date(remindAt).toISOString() : null,
      });
      setTasks((current) => [created, ...current]);
      setTitle("");
      setRemindAt("");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  /** Flip the checkbox immediately, then reconcile — or roll back on failure. */
  async function handleToggle(task: AgentTask) {
    const done = task.status !== "done";
    const previous = tasks;
    setTasks((current) =>
      current.map((t) =>
        t.id === task.id ? { ...t, status: done ? "done" : "open" } : t,
      ),
    );
    setError(null);
    try {
      const saved = done ? await completeTask(task.id) : await reopenTask(task.id);
      setTasks((current) => current.map((t) => (t.id === saved.id ? saved : t)));
    } catch (err) {
      setTasks(previous);
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function handleDelete(task: AgentTask) {
    const previous = tasks;
    setTasks((current) => current.filter((t) => t.id !== task.id));
    setError(null);
    try {
      await deleteTask(task.id);
    } catch (err) {
      setTasks(previous);
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <section aria-labelledby="tasks-heading">
      <h2 id="tasks-heading" style={{ fontSize: "1.1rem" }}>
        Tasks &amp; reminders
      </h2>

      <form onSubmit={handleAdd} style={{ ...styles.row, marginBottom: "0.75rem" }}>
        <input
          aria-label="New task"
          placeholder="Add a task…"
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          style={{ ...styles.input, flex: "1 1 12rem" }}
        />
        <input
          type="datetime-local"
          aria-label="Remind me at"
          value={remindAt}
          onChange={(event) => setRemindAt(event.target.value)}
          style={styles.input}
        />
        <button type="submit" style={styles.button} disabled={busy || title.trim() === ""}>
          Add
        </button>
      </form>

      <div style={{ ...styles.row, marginBottom: "0.5rem" }} role="group" aria-label="Filter tasks">
        {FILTERS.map((chip) => (
          <button
            key={chip.key}
            type="button"
            aria-pressed={filter === chip.key}
            onClick={() => setFilter(chip.key)}
            style={{
              ...styles.button,
              fontSize: "0.85rem",
              borderColor: filter === chip.key ? tokens.accent : tokens.border,
              color: filter === chip.key ? tokens.accent : "inherit",
            }}
          >
            {chip.label}
          </button>
        ))}
      </div>

      <ErrorBanner message={error} />

      {loading ? (
        <Loading />
      ) : visible.length === 0 ? (
        <p style={styles.muted}>
          {filter === "today"
            ? "Nothing due today."
            : tasks.length === 0
              ? "No tasks yet. Add the first one above."
              : "Nothing open — everything here is done."}
        </p>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {visible.map((task) => (
            <li key={task.id} style={{ ...styles.row, ...styles.card, gap: "0.6rem" }}>
              <input
                type="checkbox"
                aria-label={`Complete ${task.title}`}
                checked={task.status === "done"}
                onChange={() => void handleToggle(task)}
              />
              <span
                style={{
                  flex: 1,
                  textDecoration: task.status === "done" ? "line-through" : "none",
                  color: task.status === "done" ? tokens.muted : "inherit",
                }}
              >
                {task.title}
              </span>
              {task.remind_at && (
                <span
                  style={{
                    fontSize: "0.85rem",
                    color: isDueToday(task.remind_at) ? tokens.accent : tokens.muted,
                  }}
                >
                  {formatDateTime(task.remind_at)}
                </span>
              )}
              <button
                type="button"
                aria-label={`Delete ${task.title}`}
                onClick={() => void handleDelete(task)}
                style={{ ...styles.button, color: tokens.danger, fontSize: "0.8rem" }}
              >
                Delete
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
