/** Mirrors the backend Pydantic schemas in app/schemas/knowledge_base.py. */

export type ArticleKind = "faq" | "help" | "guide";
export type ArticleStatus = "draft" | "published";

export const ARTICLE_KINDS: ArticleKind[] = ["faq", "help", "guide"];
export const ARTICLE_STATUSES: ArticleStatus[] = ["draft", "published"];

export interface ArticleCategory {
  id: string;
  slug: string;
  name: string;
  description: string | null;
  sort_order: number;
  created_at: string;
  updated_at: string;
}

export interface ArticleCategoryInput {
  slug: string;
  name: string;
  description?: string | null;
  sort_order?: number;
}

export interface Article {
  id: string;
  slug: string;
  title: string;
  summary: string | null;
  body: string;
  kind: ArticleKind;
  status: ArticleStatus;
  category_id: string | null;
  view_count: number;
  author_agent_id: string | null;
  published_at: string | null;
  created_at: string;
  updated_at: string;
  category: ArticleCategory | null;
}

export interface ArticleInput {
  slug: string;
  title: string;
  summary?: string | null;
  body: string;
  kind: ArticleKind;
  status?: ArticleStatus;
  category_id?: string | null;
}

export interface ArticleSummary {
  id: string;
  slug: string;
  title: string;
  summary: string | null;
  kind: ArticleKind;
  status: ArticleStatus;
  category_id: string | null;
  updated_at: string;
}
