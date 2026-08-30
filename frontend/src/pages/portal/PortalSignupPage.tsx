import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { signup } from "../../api/portal";
import { setPortalSession } from "../../api/portalAuth";
import { ErrorBanner, styles } from "../../components/ui";

export default function PortalSignupPage() {
  const navigate = useNavigate();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const { token, portal_user } = await signup({
        email,
        password,
        display_name: displayName,
      });
      setPortalSession(token, portal_user);
      navigate("/portal/tickets");
    } catch (err) {
      // The 403 "no matching account" and 409 "already registered" cases are
      // already differentiated server-side -- just surface whatever the API said.
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <main style={styles.page}>
      <h1 style={styles.h1}>Sign up</h1>
      <p style={styles.muted}>
        Use the email address our team already has on file for you.{" "}
        <Link to="/portal/login">Log in instead</Link>
      </p>

      <ErrorBanner message={error} />

      <form onSubmit={handleSubmit} style={{ maxWidth: 400 }}>
        <div style={{ marginBottom: "1rem" }}>
          <label htmlFor="display_name" style={styles.label}>
            Your name
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
            Password (minimum 8 characters)
          </label>
          <input
            id="password"
            type="password"
            required
            minLength={8}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            style={{ ...styles.input, width: "100%" }}
          />
        </div>

        <button type="submit" style={styles.button} disabled={saving}>
          {saving ? "Signing up…" : "Sign up"}
        </button>
      </form>
    </main>
  );
}
