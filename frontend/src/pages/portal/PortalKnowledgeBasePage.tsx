import { useCallback, useEffect, useRef, useState } from "react";

import { listPortalArticles, listPortalCategories } from "../../api/portalKnowledgeBase";
import ArticleListPanel from "../../components/kb/ArticleListPanel";
import { ErrorBanner, Loading, styles, tokens } from "../../components/ui";
import type { ArticleCategory, ArticleSummary } from "../../types/knowledgeBase";

const SEARCH_DEBOUNCE_MS = 300;

export default function PortalKnowledgeBasePage() {
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [categorySlug, setCategorySlug] = useState<string>("");

  const [items, setItems] = useState<ArticleSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [categories, setCategories] = useState<ArticleCategory[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listPortalCategories()
      .then((page) => setCategories(page.items))
      .catch(() => setCategories([]));
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedSearch(search), SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [search]);

  const requestId = useRef(0);

  const load = useCallback(async () => {
    const id = ++requestId.current;
    setLoading(true);
    setError(null);
    try {
      const page = await listPortalArticles({
        categorySlug: categorySlug || undefined,
        q: debouncedSearch || undefined,
        limit: 50,
      });
      if (id !== requestId.current) return;
      setItems(page.items);
      setTotal(page.total);
    } catch (err) {
      if (id !== requestId.current) return;
      setItems([]);
      setTotal(0);
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      if (id === requestId.current) setLoading(false);
    }
  }, [categorySlug, debouncedSearch]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <main style={styles.page}>
      <h1 style={styles.h1}>Help center</h1>
      <p style={styles.muted}>{total} article(s).</p>

      <input
        type="search"
        aria-label="Search help articles"
        placeholder="Search for help…"
        value={search}
        onChange={(event) => setSearch(event.target.value)}
        style={{ ...styles.input, width: "100%", boxSizing: "border-box" }}
      />

      {categories.length > 0 && (
        <div style={{ ...styles.row, marginTop: "0.75rem" }}>
          <button
            type="button"
            onClick={() => setCategorySlug("")}
            style={{
              ...styles.button,
              borderColor: categorySlug === "" ? tokens.accent : tokens.border,
              color: categorySlug === "" ? tokens.accent : "inherit",
            }}
          >
            All
          </button>
          {categories.map((category) => (
            <button
              key={category.id}
              type="button"
              onClick={() => setCategorySlug(category.slug)}
              style={{
                ...styles.button,
                borderColor: categorySlug === category.slug ? tokens.accent : tokens.border,
                color: categorySlug === category.slug ? tokens.accent : "inherit",
              }}
            >
              {category.name}
            </button>
          ))}
        </div>
      )}

      <ErrorBanner message={error} />

      <div style={{ marginTop: "1rem" }}>
        {loading && items.length === 0 ? (
          <Loading />
        ) : (
          <ArticleListPanel
            items={items}
            categories={categories}
            getHref={(article) => `/portal/kb/${article.slug}`}
            emptyMessage="No articles match your search."
          />
        )}
      </div>
    </main>
  );
}
