/** Typed wrappers for the staff-facing knowledge-base endpoints. */

import { buildQuery, request } from "./client";
import type { Page } from "../types/customer";
import type {
  Article,
  ArticleCategory,
  ArticleCategoryInput,
  ArticleInput,
  ArticleKind,
  ArticleStatus,
  ArticleSummary,
} from "../types/knowledgeBase";

// --------------------------------------------------------------------------- //
// Categories
// --------------------------------------------------------------------------- //
export function listCategories(): Promise<Page<ArticleCategory>> {
  return request<Page<ArticleCategory>>("/kb/categories");
}

export function createCategory(payload: ArticleCategoryInput): Promise<ArticleCategory> {
  return request<ArticleCategory>("/kb/categories", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateCategory(
  id: string,
  payload: Partial<ArticleCategoryInput>,
): Promise<ArticleCategory> {
  return request<ArticleCategory>(`/kb/categories/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function deleteCategory(id: string, opts: { force?: boolean } = {}): Promise<void> {
  return request<void>(`/kb/categories/${id}${buildQuery({ force: opts.force ? "true" : undefined })}`, {
    method: "DELETE",
  });
}

// --------------------------------------------------------------------------- //
// Articles
// --------------------------------------------------------------------------- //
export function listArticles(
  params: {
    kind?: ArticleKind;
    status?: ArticleStatus;
    categoryId?: string;
    q?: string;
    limit?: number;
    offset?: number;
  } = {},
): Promise<Page<ArticleSummary>> {
  return request<Page<ArticleSummary>>(
    `/kb/articles${buildQuery({
      kind: params.kind,
      status: params.status,
      category_id: params.categoryId,
      q: params.q,
      limit: params.limit,
      offset: params.offset,
    })}`,
  );
}

export function getArticle(id: string): Promise<Article> {
  return request<Article>(`/kb/articles/${id}`);
}

export function createArticle(payload: ArticleInput): Promise<Article> {
  return request<Article>("/kb/articles", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateArticle(id: string, payload: Partial<ArticleInput>): Promise<Article> {
  return request<Article>(`/kb/articles/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function publishArticle(id: string): Promise<Article> {
  return request<Article>(`/kb/articles/${id}/publish`, { method: "POST" });
}

export function unpublishArticle(id: string): Promise<Article> {
  return request<Article>(`/kb/articles/${id}/unpublish`, { method: "POST" });
}

export function deleteArticle(id: string): Promise<void> {
  return request<void>(`/kb/articles/${id}`, { method: "DELETE" });
}
