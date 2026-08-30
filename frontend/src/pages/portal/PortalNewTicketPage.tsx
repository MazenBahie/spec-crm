import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { createPortalTicket } from "../../api/portal";
import { listCategories } from "../../api/tickets";
import type { TicketCategory } from "../../types/ticket";
import { ErrorBanner, styles } from "../../components/ui";

export default function PortalNewTicketPage() {
  const navigate = useNavigate();

  const [subject, setSubject] = useState("");
  const [description, setDescription] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [categories, setCategories] = useState<TicketCategory[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listCategories({ activeOnly: true }).then(setCategories).catch(() => setCategories([]));
  }, []);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const ticket = await createPortalTicket({
        subject: subject.trim(),
        description: description.trim(),
        category_id: categoryId || null,
      });
      navigate(`/portal/tickets/${ticket.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <main style={styles.page}>
      <h1 style={styles.h1}>New ticket</h1>
      <p style={styles.muted}>
        <Link to="/portal/tickets">Back to your tickets</Link>
      </p>

      <ErrorBanner message={error} />

      <form onSubmit={handleSubmit} style={{ maxWidth: 480 }}>
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
          <label htmlFor="description" style={styles.label}>
            Description
          </label>
          <textarea
            id="description"
            rows={6}
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            style={{ ...styles.input, width: "100%", fontFamily: "inherit" }}
          />
        </div>

        <button type="submit" style={styles.button} disabled={saving || subject.trim() === ""}>
          {saving ? "Submitting…" : "Submit ticket"}
        </button>
      </form>
    </main>
  );
}
