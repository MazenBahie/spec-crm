import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import PortalKnowledgeBasePage from "../PortalKnowledgeBasePage";
import type { ArticleCategory, ArticleSummary } from "../../../types/knowledgeBase";

function category(overrides: Partial<ArticleCategory> = {}): ArticleCategory {
  return {
    id: crypto.randomUUID(),
    slug: "billing",
    name: "Billing",
    description: null,
    sort_order: 0,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function article(overrides: Partial<ArticleSummary> = {}): ArticleSummary {
  return {
    id: crypto.randomUUID(),
    slug: "reset-password",
    title: "Reset your password",
    summary: "Quick steps",
    kind: "faq",
    status: "published",
    category_id: null,
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

interface Recorded {
  url: string;
}

function mockApi(articles: ArticleSummary[], categories: ArticleCategory[] = []) {
  const requests: Recorded[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      requests.push({ url });

      const json = (payload: unknown) =>
        new Response(JSON.stringify(payload), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });

      if (url.includes("/portal/kb/categories")) {
        return json({ items: categories, total: categories.length });
      }
      if (url.includes("/portal/kb/articles")) {
        const parsed = new URL(url, "http://x");
        const q = parsed.searchParams.get("q");
        const categorySlug = parsed.searchParams.get("category_slug");
        let filtered = articles;
        if (q) filtered = filtered.filter((a) => a.title.toLowerCase().includes(q.toLowerCase()));
        if (categorySlug) {
          const match = categories.find((c) => c.slug === categorySlug);
          filtered = filtered.filter((a) => a.category_id === match?.id);
        }
        return json({ items: filtered, total: filtered.length });
      }
      return json({ items: [], total: 0 });
    }),
  );
  return requests;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

function renderPage() {
  return render(
    <MemoryRouter>
      <PortalKnowledgeBasePage />
    </MemoryRouter>,
  );
}

describe("PortalKnowledgeBasePage", () => {
  it("lists published articles", async () => {
    mockApi([article({ title: "Reset your password" }), article({ title: "Billing FAQ" })]);
    renderPage();

    expect(await screen.findByText("Reset your password")).toBeInTheDocument();
    expect(screen.getByText("Billing FAQ")).toBeInTheDocument();
  });

  it("searches articles", async () => {
    const requests = mockApi([
      article({ title: "Reset your password" }),
      article({ title: "Billing FAQ" }),
    ]);
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("Reset your password");
    await user.type(screen.getByLabelText("Search help articles"), "billing");

    await waitFor(() => expect(screen.queryByText("Reset your password")).not.toBeInTheDocument());
    expect(screen.getByText("Billing FAQ")).toBeInTheDocument();
    expect(requests.some((r) => r.url.includes("q=billing"))).toBe(true);
  });

  it("filters by category chip", async () => {
    const billing = category({ slug: "billing", name: "Billing" });
    mockApi(
      [
        article({ title: "In billing", category_id: billing.id }),
        article({ title: "General", category_id: null }),
      ],
      [billing],
    );
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("In billing");
    await user.click(screen.getByRole("button", { name: "Billing" }));

    await waitFor(() => expect(screen.queryByText("General")).not.toBeInTheDocument());
    expect(screen.getByText("In billing")).toBeInTheDocument();
  });

  it("shows an empty state", async () => {
    mockApi([]);
    renderPage();

    expect(await screen.findByText("No articles match your search.")).toBeInTheDocument();
  });
});
