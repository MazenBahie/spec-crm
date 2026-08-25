import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { createCustomer, getCustomer, updateCustomer } from "../api/customers";
import { ErrorBanner, Loading, styles } from "../components/ui";

/** Create when the route carries no id, otherwise edit that customer. */
export default function CustomerEditPage() {
  const { id } = useParams<{ id: string }>();
  const isEdit = Boolean(id);
  const navigate = useNavigate();

  const [displayName, setDisplayName] = useState("");
  const [company, setCompany] = useState("");
  const [loading, setLoading] = useState(isEdit);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    setLoading(true);
    getCustomer(id)
      .then((customer) => {
        if (cancelled) return;
        setDisplayName(customer.display_name);
        setCompany(customer.company ?? "");
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
      const payload = {
        display_name: displayName.trim(),
        company: company.trim() || null,
      };
      const saved = id
        ? await updateCustomer(id, payload)
        : await createCustomer(payload);
      navigate(`/customers/${saved.id}`);
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

  return (
    <main style={styles.page}>
      <h1 style={styles.h1}>{isEdit ? "Edit customer" : "New customer"}</h1>
      <p style={styles.muted}>
        <Link to={isEdit ? `/customers/${id}` : "/customers"}>Back</Link>
      </p>

      <ErrorBanner message={error} />

      <form onSubmit={handleSubmit} style={{ maxWidth: 480 }}>
        <div style={{ marginBottom: "1rem" }}>
          <label htmlFor="display_name" style={styles.label}>
            Name (required)
          </label>
          <input
            id="display_name"
            required
            value={displayName}
            onChange={(event) => setDisplayName(event.target.value)}
            style={{ ...styles.input, width: "100%" }}
          />
        </div>

        <div style={{ marginBottom: "1rem" }}>
          <label htmlFor="company" style={styles.label}>
            Company
          </label>
          <input
            id="company"
            value={company}
            onChange={(event) => setCompany(event.target.value)}
            style={{ ...styles.input, width: "100%" }}
          />
        </div>

        <div style={styles.row}>
          <button
            type="submit"
            style={styles.button}
            disabled={saving || displayName.trim() === ""}
          >
            {saving ? "Saving…" : isEdit ? "Save changes" : "Create customer"}
          </button>
          <button
            type="button"
            style={styles.button}
            onClick={() => navigate(isEdit ? `/customers/${id}` : "/customers")}
            disabled={saving}
          >
            Cancel
          </button>
        </div>
      </form>
    </main>
  );
}
