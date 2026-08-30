import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { login } from "../../api/portal";
import { setPortalSession } from "../../api/portalAuth";
import { ErrorBanner, styles } from "../../components/ui";

export default function PortalLoginPage() {
  const navigate = useNavigate();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const { token, portal_user } = await login({ email, password });
      setPortalSession(token, portal_user);
      navigate("/portal/tickets");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <main style={styles.page}>
      <h1 style={styles.h1}>Log in</h1>
      <p style={styles.muted}>
        No account yet? <Link to="/portal/signup">Sign up</Link>
      </p>

      <ErrorBanner message={error} />

      <form onSubmit={handleSubmit} style={{ maxWidth: 400 }}>
        <div style={{ marginBottom: "1rem" }}>
          <label htmlFor="email" style={styles.label}>
            Email
          </label>
          <input
            id="email"
            type="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            style={{ ...styles.input, width: "100%" }}
          />
        </div>

        <div style={{ marginBottom: "1rem" }}>
          <label htmlFor="password" style={styles.label}>
            Password
          </label>
          <input
            id="password"
            type="password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            style={{ ...styles.input, width: "100%" }}
          />
        </div>

        <button type="submit" style={styles.button} disabled={saving}>
          {saving ? "Logging in…" : "Log in"}
        </button>
      </form>
    </main>
  );
}
