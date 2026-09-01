import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { getPortalArticle } from "../../api/portalKnowledgeBase";
import { ApiError } from "../../api/client";
import { ErrorBanner, Loading, styles } from "../../components/ui";
import type { Article } from "../../types/knowledgeBase";

export default function PortalArticlePage() {
  const { slug } = useParams<{ slug: string }>();
  const [article, setArticle] = useState<Article | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!slug) return;
    let cancelled = false;
    setLoading(true);
    setNotFound(false);
    setError(null);
    getPortalArticle(slug)
      .then((result) => {
        if (!cancelled) setArticle(result);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 404) {
          setNotFound(true);
        } else {
          setError(err instanceof Error ? err.message : String(err));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [slug]);

  return (
    <main style={styles.page}>
      <p style={styles.muted}>
        <Link to="/portal/kb">Back to help center</Link>
      </p>

      <ErrorBanner message={error} />

      {loading ? (
        <Loading />
      ) : notFound ? (
        <>
          <h1 style={styles.h1}>Article not found</h1>
          <p style={styles.muted}>This article does not exist or is no longer available.</p>
        </>
      ) : article ? (
        <>
          <h1 style={styles.h1}>{article.title}</h1>
          {article.summary && <p style={styles.muted}>{article.summary}</p>}
          {/* TODO(knowledge-base story): render `body` as markdown once a
              renderer is added to the project; plain text avoids injecting
              raw HTML in the meantime. */}
          <pre
            style={{
              whiteSpace: "pre-wrap",
              fontFamily: "inherit",
              lineHeight: 1.6,
              marginTop: "1.5rem",
            }}
          >
            {article.body}
          </pre>
        </>
      ) : null}
    </main>
  );
}
