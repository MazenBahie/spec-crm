import { useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { listCustomers } from "../api/customers";
import { createTicket, getTicket, listAgents, listCategories, updateTicket } from "../api/tickets";
import { ErrorBanner, Loading, styles } from "../components/ui";
import type { Customer } from "../types/customer";
import type { Agent, TicketCategory, TicketPriority } from "../types/ticket";
import { TICKET_PRIORITIES } from "../types/ticket";

/** Create when the route carries no id, otherwise edit that ticket. */
export default function TicketEditPage() {
  const { id } = useParams<{ id: string }>();
  const [searchParams] = useSearchParams();
  const isEdit = Boolean(id);
  const navigate = useNavigate();

  const [customerId, setCustomerId] = useState(searchParams.get("customerId") ?? "");
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [subject, setSubject] = useState("");
  const [description, setDescription] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [priority, setPriority] = useState<TicketPriority | "">("");
  const [assigneeId, setAssigneeId] = useState("");
  const [categories, setCategories] = useState<TicketCategory[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);

  const [loading, setLoading] = useState(isEdit);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listCategories({ activeOnly: true }).then(setCategories).catch(() => setCategories([]));
    listAgents({ activeOnly: true }).then(setAgents).catch(() => setAgents([]));
    if (!customerId) {
      listCustomers({ limit: 100 }).then((page) => setCustomers(page.items)).catch(() => setCustomers([]));
    }
  }, [customerId]);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    setLoading(true);
    getTicket(id)
      .then((ticket) => {
        if (cancelled) return;
        setCustomerId(ticket.customer_id);
        setSubject(ticket.subject);
        setDescription(ticket.description);
        setCategoryId(ticket.category_id ?? "");
        setPriority(ticket.priority);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      if (id) {
        const saved = await updateTicket(id, {
          subject: subject.trim(),
          description,
          category_id: categoryId || null,
          priority: priority || undefined,
        });
        navigate(`/tickets/${saved.id}`);
      } else {
        const saved = await createTicket({
          customer_id: customerId,
          subject: subject.trim(),
          description,
          category_id: categoryId || null,
          priority: priority || null,
          assignee_id: assigneeId || null,
        });
        navigate(`/tickets/${saved.id}`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <main style={styles.page}>
        <Loading />
      </main>
    );
  }

  const backTo = isEdit ? `/tickets/${id}` : customerId ? `/customers/${customerId}` : "/tickets";

  return (
    <main style={styles.page}>
      <h1 style={styles.h1}>{isEdit ? "Edit ticket" : "New ticket"}</h1>
      <p style={styles.muted}>
        <Link to={backTo}>Back</Link>
      </p>

      <ErrorBanner message={error} />

      <form onSubmit={handleSubmit} style={{ maxWidth: 480 }}>
        {!isEdit && (
          <div style={{ marginBottom: "1rem" }}>
            <label htmlFor="customer" style={styles.label}>
              Customer (required)
            </label>
            {searchParams.get("customerId") ? (
              <input
                id="customer"
                value={customers.find((c) => c.id === customerId)?.display_name ?? customerId}
                disabled
                style={{ ...styles.input, width: "100%" }}
              />
            ) : (
              <select
                id="customer"
                required
                value={customerId}
                onChange={(event) => setCustomerId(event.target.value)}
                style={{ ...styles.input, width: "100%" }}
              >
                <option value="">Select a customer…</option>
                {customers.map((customer) => (
                  <option key={customer.id} value={customer.id}>
                    {customer.display_name}
                  </option>
                ))}
              </select>
            )}
          </div>
        )}

        <div style={{ marginBottom: "1rem" }}>
          <label htmlFor="subject" style={styles.label}>
            Subject (required)
          </label>
          <input
            id="subject"
            required
            value={subject}
            onChange={(event) => setSubject(event.target.value)}
            style={{ ...styles.input, width: "100%" }}
          />
        </div>

        <div style={{ marginBottom: "1rem" }}>
          <label htmlFor="description" style={styles.label}>
            Description
          </label>
          <textarea
            id="description"
            rows={4}
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            style={{ ...styles.input, width: "100%" }}
          />
        </div>

        <div style={{ marginBottom: "1rem" }}>
          <label htmlFor="category" style={styles.label}>
            Category
          </label>
          <select
            id="category"
            value={categoryId}
            onChange={(event) => setCategoryId(event.target.value)}
            style={{ ...styles.input, width: "100%" }}
          >
            <option value="">No category</option>
            {categories.map((category) => (
              <option key={category.id} value={category.id}>
                {category.name}
              </option>
            ))}
          </select>
        </div>

        <div style={{ marginBottom: "1rem" }}>
          <label htmlFor="priority" style={styles.label}>
            Priority {!isEdit && "(defaults to the category's, or normal)"}
          </label>
          <select
            id="priority"
            value={priority}
            onChange={(event) => setPriority(event.target.value as TicketPriority | "")}
            style={{ ...styles.input, width: "100%" }}
          >
            <option value="">
              {isEdit ? "Keep current" : "Inherit from category"}
            </option>
            {TICKET_PRIORITIES.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </div>

        {!isEdit && (
          <div style={{ marginBottom: "1rem" }}>
            <label htmlFor="assignee" style={styles.label}>
              Assignee
            </label>
            <select
              id="assignee"
              value={assigneeId}
              onChange={(event) => setAssigneeId(event.target.value)}
              style={{ ...styles.input, width: "100%" }}
            >
              <option value="">Unassigned</option>
              {agents.map((agent) => (
                <option key={agent.id} value={agent.id}>
                  {agent.display_name}
                </option>
              ))}
            </select>
          </div>
        )}

        <div style={styles.row}>
          <button
            type="submit"
            style={styles.button}
            disabled={saving || subject.trim() === "" || (!isEdit && customerId === "")}
          >
            {saving ? "Saving…" : isEdit ? "Save changes" : "Create ticket"}
          </button>
          <button type="button" style={styles.button} onClick={() => navigate(backTo)} disabled={saving}>
            Cancel
          </button>
        </div>
      </form>
    </main>
  );
}
