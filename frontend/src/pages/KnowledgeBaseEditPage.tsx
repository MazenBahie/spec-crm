import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import {
  createArticle,
  deleteArticle,
  getArticle,
  listCategories,
  publishArticle,
  unpublishArticle,
  updateArticle,
} from "../api/knowledgeBase";
import { ErrorBanner, Loading, styles } from "../components/ui";
import { ARTICLE_KINDS } from "../types/knowledgeBase";
import type { ArticleCategory, ArticleKind } from "../types/knowledgeBase";

/** `my-article-title` from `My Article Title` -- a starting point, still editable. */
function slugify(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

/** Create when the route carries no id, otherwise edit that article. */
export default function KnowledgeBaseEditPage() {
  const { id } = useParams<{ id: string }>();
  const isEdit = Boolean(id);
  const navigate = useNavigate();

  const [slug, setSlug] = useState("");
  const [slugTouched, setSlugTouched] = useState(false);
  const [title, setTitle] = useState("");
  const [summary, setSummary] = useState("");
  const [body, setBody] = useState("");
  const [kind, setKind] = useState<ArticleKind>("faq");
  const [categoryId, setCategoryId] = useState("");
  const [status, setStatus] = useState<"draft" | "published">("draft");
  const [categories, setCategories] = useState<ArticleCategory[]>([]);

  const [loading, setLoading] = useState(isEdit);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listCategories()
      .then((page) => setCategories(page.items))
      .catch(() => setCategories([]));
  }, []);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    setLoading(true);
    getArticle(id)
      .then((article) => {
        if (cancelled) return;
        setSlug(article.slug);
        setSlugTouched(true);
        setTitle(article.title);
        setSummary(article.summary ?? "");
        setBody(article.body);
        setKind(article.kind);
        setCategoryId(article.category_id ?? "");
        setStatus(article.status);
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
        slug: slug.trim(),
        title: title.trim(),
        summary: summary.trim() || null,
        body,
        kind,
        category_id: categoryId || null,
      };
      const saved = id
        ? await updateArticle(id, payload)
        : await createArticle({ ...payload, status });
      navigate(`/kb/${saved.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }

  async function guard(action: () => Promise<void>) {
    setError(null);
    setSaving(true);
    try {
      await action();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }

  async function handlePublish() {
    if (!id) return;
    await guard(async () => {
      const saved = await publishArticle(id);
      setStatus(saved.status);
    });
  }

  async function handleUnpublish() {
    if (!id) return;
    await guard(async () => {
      const saved = await unpublishArticle(id);
      setStatus(saved.status);
    });
  }

  async function handleDelete() {
    if (!id) return;
    if (!window.confirm("Delete this article? This cannot be undone.")) return;
    await guard(async () => {
      await deleteArticle(id);
      navigate("/kb");
    });
  }

  if (loading) {
    return (
      <main style={styles.page}>
        <Loading />
      </main>
    );
  }

  const backTo = id ? `/kb/${id}` : "/kb";

  return (
    <main style={styles.page}>
      <h1 style={styles.h1}>{isEdit ? "Edit article" : "New article"}</h1>
      <p style={styles.muted}>
        <Link to="/kb">Back to knowledge base</Link>
      </p>

      <ErrorBanner message={error} />

      {isEdit && (
        <div style={{ ...styles.row, marginBottom: "1rem" }}>
          <span style={styles.muted}>Status: {status}</span>
          {status === "draft" ? (
            <button type="button" style={styles.button} onClick={() => void handlePublish()} disabled={saving}>
              Publish
            </button>
          ) : (
            <button type="button" style={styles.button} onClick={() => void handleUnpublish()} disabled={saving}>
              Unpublish
            </button>
          )}
          <button
            type="button"
            style={{ ...styles.button, marginLeft: "auto" }}
            onClick={() => void handleDelete()}
            disabled={saving}
          >
            Delete
          </button>
        </div>
      )}

      <form onSubmit={handleSubmit} style={{ maxWidth: 640 }}>
        <div style={{ marginBottom: "1rem" }}>
          <label htmlFor="title" style={styles.label}>
            Title (required)
          </label>
          <input
            id="title"
            required
            value={title}
            onChange={(event) => {
              const value = event.target.value;
              setTitle(value);
              if (!slugTouched) setSlug(slugify(value));
            }}
            style={{ ...styles.input, width: "100%" }}
          />
        </div>

        <div style={{ marginBottom: "1rem" }}>
          <label htmlFor="slug" style={styles.label}>
            Slug (required)
          </label>
          <input
            id="slug"
            required
            value={slug}
            onChange={(event) => {
              setSlug(event.target.value);
              setSlugTouched(true);
            }}
            style={{ ...styles.input, width: "100%" }}
          />
        </div>

        <div style={{ marginBottom: "1rem" }}>
          <label htmlFor="kind" style={styles.label}>
            Kind
          </label>
          <select
            id="kind"
            value={kind}
            onChange={(event) => setKind(event.target.value as ArticleKind)}
            style={{ ...styles.input, width: "100%" }}
          >
            {ARTICLE_KINDS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
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
          <label htmlFor="summary" style={styles.label}>
            Summary
          </label>
          <input
            id="summary"
            value={summary}
            onChange={(event) => setSummary(event.target.value)}
            style={{ ...styles.input, width: "100%" }}
          />
        </div>

        <div style={{ marginBottom: "1rem" }}>
          <label htmlFor="body" style={styles.label}>
            Body (markdown)
          </label>
          <textarea
            id="body"
            rows={12}
            value={body}
            onChange={(event) => setBody(event.target.value)}
            style={{ ...styles.input, width: "100%", boxSizing: "border-box", fontFamily: "monospace" }}
          />
        </div>

        {!isEdit && (
          <div style={{ marginBottom: "1rem" }}>
            <label htmlFor="status" style={styles.label}>
              Status
            </label>
            <select
              id="status"
              value={status}
              onChange={(event) => setStatus(event.target.value as "draft" | "published")}
              style={{ ...styles.input, width: "100%" }}
            >
              <option value="draft">Draft</option>
              <option value="published">Published</option>
            </select>
          </div>
        )}

        <div style={styles.row}>
          <button
            type="submit"
            style={styles.button}
            disabled={saving || title.trim() === "" || slug.trim() === "" || (isEdit ? false : body.trim() === "" && status === "published")}
          >
            {saving ? "Saving…" : isEdit ? "Save changes" : "Create article"}
          </button>
          <button type="button" style={styles.button} onClick={() => navigate(backTo)} disabled={saving}>
            Cancel
          </button>
        </div>
      </form>
    </main>
  );
}
