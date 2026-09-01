import { useEffect, useState } from "react";

import { recomputeSuggestedCategory } from "../../api/ai";
import { listCategories, updateTicket } from "../../api/tickets";
import { ErrorBanner, styles, tokens } from "../ui";
import type { TicketDetail } from "../../types/ticket";

interface Props {
  ticket: TicketDetail;
  onChanged: () => void;
}

export default function CategorySuggestion({ ticket, onChanged }: Props) {
  const [anyCategories, setAnyCategories] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listCategories({ activeOnly: true })
      .then((cats) => setAnyCategories(cats.length > 0))
      .catch(() => setAnyCategories(false));
  }, []);

  // Nothing configured to suggest from -- suppress the whole control,
  // Apply button included, rather than show a recompute button that can
  // only ever come back empty.
  if (!anyCategories) return null;

  const suggestion = ticket.ai_suggested_category;
  const alreadyCurrent = suggestion !== null && suggestion.id === ticket.category_id;

  async function handleRecompute() {
    setBusy(true);
    setError(null);
    try {
      await recomputeSuggestedCategory(ticket.id);
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleApply() {
    if (!suggestion) return;
    setBusy(true);
    setError(null);
    try {
      await updateTicket(ticket.id, { category_id: suggestion.id });
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ marginTop: "0.4rem" }}>
      <ErrorBanner message={error} />
      {suggestion && !alreadyCurrent && (
        <p style={{ margin: "0 0 0.4rem", ...styles.muted }}>
          <span
            style={{
              border: `1px dashed ${tokens.accent}`,
              borderRadius: 4,
              padding: "0 4px",
              fontSize: "0.75rem",
              marginRight: "0.4rem",
            }}
            title="AI-generated suggestion"
          >
            AI
          </span>
          Suggests: {suggestion.name}{" "}
          <button type="button" style={styles.button} disabled={busy} onClick={() => void handleApply()}>
            Apply
          </button>
        </p>
      )}
      <button
        type="button"
        style={{ ...styles.button, fontSize: "0.8rem" }}
        disabled={busy}
        onClick={() => void handleRecompute()}
      >
        {suggestion ? "Recompute suggestion" : "Suggest category"}
      </button>
    </div>
  );
}
