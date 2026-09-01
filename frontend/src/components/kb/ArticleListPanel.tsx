/** Shared article-list rendering for both the agent and portal KB pages.
 *
 * They differ only in whether a status badge is shown (drafts only exist on
 * the agent side -- the portal never receives one) and where each row links.
 */

import { Link } from "react-router-dom";

import type { ArticleCategory, ArticleSummary } from "../../types/knowledgeBase";
import { formatDateTime, styles, tokens } from "../ui";

function KindBadge({ kind }: { kind: ArticleSummary["kind"] }) {
  return (
    <span
      style={{
        fontSize: "0.75rem",
        textTransform: "uppercase",
        letterSpacing: "0.05em",
        padding: "0.15rem 0.45rem",
        borderRadius: 10,
        border: `1px solid ${tokens.muted}`,
        color: tokens.muted,
      }}
    >
      {kind}
    </span>
  );
}

function StatusBadge({ status }: { status: ArticleSummary["status"] }) {
  const published = status === "published";
  return (
    <span
      style={{
        fontSize: "0.75rem",
        textTransform: "uppercase",
        letterSpacing: "0.05em",
        padding: "0.15rem 0.45rem",
        borderRadius: 10,
        border: `1px solid ${published ? tokens.accent : tokens.danger}`,
        color: published ? tokens.accent : tokens.danger,
      }}
    >
      {status}
    </span>
  );
}

export interface ArticleListPanelProps {
  items: ArticleSummary[];
  categories?: ArticleCategory[];
  getHref: (article: ArticleSummary) => string;
  showStatus?: boolean;
  emptyMessage?: string;
}

export default function ArticleListPanel({
  items,
  categories = [],
  getHref,
  showStatus = false,
  emptyMessage = "No articles found.",
}: ArticleListPanelProps) {
  function categoryName(categoryId: string | null): string | null {
    if (!categoryId) return null;
    return categories.find((c) => c.id === categoryId)?.name ?? null;
  }

  if (items.length === 0) {
    return <p style={styles.muted}>{emptyMessage}</p>;
  }

  return (
    <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
      {items.map((article) => (
        <li key={article.id} style={styles.card}>
          <div style={{ ...styles.row, justifyContent: "space-between" }}>
            <span style={styles.row}>
              <Link to={getHref(article)}>
                <strong>{article.title}</strong>
              </Link>
              <KindBadge kind={article.kind} />
              {showStatus && <StatusBadge status={article.status} />}
              {categoryName(article.category_id) && (
                <span style={{ color: tokens.muted, fontSize: "0.85rem" }}>
                  {categoryName(article.category_id)}
                </span>
              )}
            </span>
            <span style={{ ...styles.muted, fontSize: "0.85rem", margin: 0 }}>
              Updated {formatDateTime(article.updated_at)}
            </span>
          </div>
          {article.summary && (
            <p style={{ margin: "0.5rem 0 0", color: tokens.muted, fontSize: "0.9rem" }}>
              {article.summary}
            </p>
          )}
        </li>
      ))}
    </ul>
  );
}
