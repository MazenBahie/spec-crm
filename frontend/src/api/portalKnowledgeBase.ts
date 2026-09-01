/** Typed wrappers for the public / portal knowledge-base endpoints. */

import { buildQuery } from "./client";
import { requestPortal } from "./portalClient";
import type { Page } from "../types/customer";
import type { Article, ArticleCategory, ArticleKind, ArticleSummary } from "../types/knowledgeBase";

export function listPortalCategories(): Promise<Page<ArticleCategory>> {
  return requestPortal<Page<ArticleCategory>>("/portal/kb/categories");
}

export function listPortalArticles(
  params: {
    kind?: ArticleKind;
    categorySlug?: string;
    q?: string;
    limit?: number;
    offset?: number;
  } = {},
): Promise<Page<ArticleSummary>> {
  return requestPortal<Page<ArticleSummary>>(
    `/portal/kb/articles${buildQuery({
      kind: params.kind,
      category_slug: params.categorySlug,
      q: params.q,
      limit: params.limit,
      offset: params.offset,
    })}`,
  );
}

export function getPortalArticle(slug: string): Promise<Article> {
  return requestPortal<Article>(`/portal/kb/articles/${slug}`);
}
