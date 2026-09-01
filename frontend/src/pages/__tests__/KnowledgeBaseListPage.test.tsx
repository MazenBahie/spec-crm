import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import KnowledgeBaseListPage from "../KnowledgeBaseListPage";
import type { ArticleCategory, ArticleSummary } from "../../types/knowledgeBase";

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
    summary: "Quick steps to reset",
    kind: "faq",
    status: "draft",
    category_id: null,
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

interface Recorded {
  method: string;
  url: string;
}

function mockApi(articles: ArticleSummary[], categories: ArticleCategory[] = []) {
  const requests: Recorded[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = (init?.method ?? "GET").toUpperCase();
      requests.push({ method, url });

      const json = (payload: unknown, status = 200) =>
        new Response(status === 204 ? null : JSON.stringify(payload), {
          status,
          headers: { "Content-Type": "application/json" },
        });

      if (url.includes("/kb/categories")) return json({ items: categories, total: categories.length });
      if (url.includes("/kb/articles")) {
        const q = new URL(url, "http://x").searchParams.get("q");
        const filtered = q
          ? articles.filter((a) => a.title.toLowerCase().includes(q.toLowerCase()))
          : articles;
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
      <KnowledgeBaseListPage />
    </MemoryRouter>,
  );
}

describe("KnowledgeBaseListPage", () => {
  it("renders the article list", async () => {
    mockApi([article({ title: "Reset your password" }), article({ title: "Billing FAQ" })]);
    renderPage();

    expect(await screen.findByText("Reset your password")).toBeInTheDocument();
    expect(screen.getByText("Billing FAQ")).toBeInTheDocument();
  });

  it("shows an empty state when nothing matches", async () => {
    mockApi([]);
    renderPage();

    expect(await screen.findByText("No articles match these filters.")).toBeInTheDocument();
  });

  it("filters by kind", async () => {
    const requests = mockApi([article()]);
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("Reset your password");
    await user.selectOptions(screen.getByLabelText("Filter by kind"), "guide");

    await waitFor(() =>
      expect(requests.some((r) => r.url.includes("kind=guide"))).toBe(true),
    );
  });

  it("filters by status", async () => {
    const requests = mockApi([article()]);
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("Reset your password");
    await user.selectOptions(screen.getByLabelText("Filter by status"), "published");

    await waitFor(() =>
      expect(requests.some((r) => r.url.includes("status=published"))).toBe(true),
    );
  });

  it("submits a search query", async () => {
    const requests = mockApi([
      article({ title: "Reset your password" }),
      article({ title: "Billing FAQ" }),
    ]);
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("Reset your password");
    await user.type(screen.getByLabelText("Search articles"), "billing");

    await waitFor(() => expect(screen.queryByText("Reset your password")).not.toBeInTheDocument());
    expect(screen.getByText("Billing FAQ")).toBeInTheDocument();
    expect(requests.some((r) => r.url.includes("q=billing"))).toBe(true);
  });

  it("opens and closes the category management drawer", async () => {
    mockApi([], [category()]);
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("Knowledge base");
    expect(screen.queryByText("Categories")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Manage categories" }));
    const drawer = (await screen.findByText("Categories")).closest("div")!;
    expect(within(drawer).getByText(/Billing/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Hide categories" }));
    expect(screen.queryByText("Categories")).not.toBeInTheDocument();
  });

  it("links to the new-article page", async () => {
    mockApi([]);
    renderPage();

    await screen.findByText("No articles match these filters.");
    expect(screen.getByRole("link", { name: "New article" })).toHaveAttribute("href", "/kb/new");
  });
});
