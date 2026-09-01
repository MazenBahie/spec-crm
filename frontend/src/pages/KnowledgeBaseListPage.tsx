import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import {
  createCategory,
  deleteCategory,
  listArticles,
  listCategories,
} from "../api/knowledgeBase";
import ArticleListPanel from "../components/kb/ArticleListPanel";
import { ErrorBanner, Loading, styles } from "../components/ui";
import { ARTICLE_KINDS, ARTICLE_STATUSES } from "../types/knowledgeBase";
import type {
  ArticleCategory,
  ArticleKind,
  ArticleStatus,
  ArticleSummary,
} from "../types/knowledgeBase";

const PAGE_SIZE = 20;
const SEARCH_DEBOUNCE_MS = 300;

function CategoryDrawer({
  categories,
  onChanged,
}: {
  categories: ArticleCategory[];
  onChanged: () => void;
}) {
  const [slug, setSlug] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleCreate(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await createCategory({ slug: slug.trim(), name: name.trim() });
      setSlug("");
      setName("");
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete(category: ArticleCategory) {
    if (!window.confirm(`Delete the category "${category.name}"?`)) return;
    setError(null);
    try {
      await deleteCategory(category.id);
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <div style={{ ...styles.card, marginTop: "1rem" }}>
      <h2 style={{ fontSize: "1rem", marginTop: 0 }}>Categories</h2>
      <ErrorBanner message={error} />
      <form onSubmit={handleCreate} style={styles.row}>
        <input
          aria-label="New category slug"
          placeholder="slug"
          value={slug}
          onChange={(event) => setSlug(event.target.value)}
          style={{ ...styles.input, width: "10rem" }}
        />
        <input
          aria-label="New category name"
          placeholder="Name"
          value={name}
          onChange={(event) => setName(event.target.value)}
          style={{ ...styles.input, flex: "1 1 10rem" }}
        />
        <button
          type="submit"
          style={styles.button}
          disabled={busy || slug.trim() === "" || name.trim() === ""}
        >
          Add category
        </button>
      </form>

      {categories.length === 0 ? (
        <p style={styles.muted}>No categories yet.</p>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, marginTop: "0.75rem" }}>
          {categories.map((category) => (
            <li
              key={category.id}
              style={{ ...styles.row, justifyContent: "space-between", padding: "0.25rem 0" }}
            >
              <span>
                {category.name} <span style={{ color: "#666" }}>({category.slug})</span>
              </span>
              <button
                type="button"
                aria-label={`Delete category ${category.name}`}
                style={{ ...styles.button, fontSize: "0.8rem" }}
                onClick={() => void handleDelete(category)}
              >
                Delete
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function KnowledgeBaseListPage() {
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [kind, setKind] = useState<ArticleKind | "">("");
  const [status, setStatus] = useState<ArticleStatus | "">("");
  const [categoryId, setCategoryId] = useState("");
  const [offset, setOffset] = useState(0);
  const [showCategories, setShowCategories] = useState(false);

  const [items, setItems] = useState<ArticleSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [categories, setCategories] = useState<ArticleCategory[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadCategories = useCallback(async () => {
    try {
      const page = await listCategories();
      setCategories(page.items);
    } catch {
      setCategories([]);
    }
  }, []);

  useEffect(() => {
    void loadCategories();
  }, [loadCategories]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setDebouncedSearch(search);
      setOffset(0);
    }, SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [search]);

  // Ignore responses from superseded requests so a slow early fetch cannot
  // overwrite a newer one -- same guard as TicketsListPage.
  const requestId = useRef(0);

  const load = useCallback(async () => {
    const id = ++requestId.current;
    setLoading(true);
    setError(null);
    try {
      const page = await listArticles({
        kind: kind || undefined,
        status: status || undefined,
        categoryId: categoryId || undefined,
        q: debouncedSearch || undefined,
        limit: PAGE_SIZE,
        offset,
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
  }, [kind, status, categoryId, debouncedSearch, offset]);

  useEffect(() => {
    void load();
  }, [load]);

  const page = Math.floor(offset / PAGE_SIZE) + 1;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <main style={styles.page}>
      <div style={{ ...styles.row, justifyContent: "space-between" }}>
        <div>
          <h1 style={styles.h1}>Knowledge base</h1>
          <p style={styles.muted}>{total} article(s) match the current filters.</p>
        </div>
        <div style={styles.row}>
          <button
            type="button"
            style={styles.button}
            onClick={() => setShowCategories((current) => !current)}
          >
            {showCategories ? "Hide categories" : "Manage categories"}
          </button>
          <Link to="/kb/new" style={{ ...styles.button, textDecoration: "none" }}>
            New article
          </Link>
        </div>
      </div>

      {showCategories && <CategoryDrawer categories={categories} onChanged={loadCategories} />}

      <div style={{ ...styles.row, marginTop: "1rem" }}>
        <input
          type="search"
          aria-label="Search articles"
          placeholder="Search title, summary, body…"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          style={{ ...styles.input, flex: "1 1 16rem" }}
        />
        <select
          aria-label="Filter by kind"
          value={kind}
          onChange={(event) => {
            setKind(event.target.value as ArticleKind | "");
            setOffset(0);
          }}
          style={styles.input}
        >
          <option value="">All kinds</option>
          {ARTICLE_KINDS.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
        <select
          aria-label="Filter by status"
          value={status}
          onChange={(event) => {
            setStatus(event.target.value as ArticleStatus | "");
            setOffset(0);
          }}
          style={styles.input}
        >
          <option value="">All statuses</option>
          {ARTICLE_STATUSES.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
        <select
          aria-label="Filter by category"
          value={categoryId}
          onChange={(event) => {
            setCategoryId(event.target.value);
            setOffset(0);
          }}
          style={styles.input}
        >
          <option value="">All categories</option>
          {categories.map((category) => (
            <option key={category.id} value={category.id}>
              {category.name}
            </option>
          ))}
        </select>
      </div>

      <ErrorBanner message={error} />

      <div style={{ marginTop: "1rem" }}>
        {loading && items.length === 0 ? (
          <Loading />
        ) : (
          <ArticleListPanel
            items={items}
            categories={categories}
            getHref={(article) => `/kb/${article.id}`}
            showStatus
            emptyMessage="No articles match these filters."
          />
        )}
      </div>

      <div style={{ ...styles.row, marginTop: "1rem" }}>
        <button
          type="button"
          style={styles.button}
          onClick={() => setOffset((current) => Math.max(0, current - PAGE_SIZE))}
          disabled={offset === 0 || loading}
        >
          Previous
        </button>
        <span style={styles.muted}>
          Page {page} of {pageCount}
        </span>
        <button
          type="button"
          style={styles.button}
          onClick={() => setOffset((current) => current + PAGE_SIZE)}
          disabled={offset + PAGE_SIZE >= total || loading}
        >
          Next
        </button>
      </div>
    </main>
  );
}
