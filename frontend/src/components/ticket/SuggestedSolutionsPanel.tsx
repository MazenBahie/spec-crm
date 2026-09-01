import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { getSuggestedSolutions } from "../../api/ai";
import { ErrorBanner, Loading, styles, tokens } from "../ui";
import type { ArticleSummary } from "../../types/knowledgeBase";

interface Props {
  ticketId: string;
}

export default function SuggestedSolutionsPanel({ ticketId }: Props) {
  const [articles, setArticles] = useState<ArticleSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setArticles(await getSuggestedSolutions(ticketId));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [ticketId]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <section style={{ ...styles.card, marginTop: "1rem" }}>
      <div style={{ ...styles.row, justifyContent: "space-between" }}>
        <h2 style={{ fontSize: "1.1rem", margin: 0 }}>
          Suggested Solutions{" "}
          <span
            style={{
              fontSize: "0.7rem",
              textTransform: "uppercase",
              letterSpacing: "0.05em",
              padding: "0.1rem 0.4rem",
              borderRadius: 8,
              border: `1px solid ${tokens.accent}`,
              color: tokens.accent,
            }}
          >
            AI
          </span>
        </h2>
        <button type="button" style={{ ...styles.button, fontSize: "0.8rem" }} onClick={() => void load()}>
          Refresh
        </button>
      </div>
      <p style={{ ...styles.muted, fontSize: "0.85rem" }}>
        Ranked by AI from published knowledge-base articles — links only, nothing is applied to
        this ticket automatically.
      </p>

      {loading ? (
        <Loading />
      ) : error ? (
        <ErrorBanner message={error} />
      ) : articles.length === 0 ? (
        <p style={styles.muted}>No matching knowledge base articles found.</p>
      ) : (
        <ul style={{ paddingLeft: "1.25rem", margin: 0 }}>
          {articles.map((article) => (
            <li key={article.id} style={{ marginBottom: "0.5rem" }}>
              <Link to={`/kb/${article.id}`}>{article.title}</Link>
              {article.summary && (
                <p style={{ ...styles.muted, margin: "0.2rem 0 0", fontSize: "0.85rem" }}>
                  {article.summary}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
