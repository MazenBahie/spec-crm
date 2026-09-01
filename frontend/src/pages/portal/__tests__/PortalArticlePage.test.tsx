import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import PortalArticlePage from "../PortalArticlePage";
import type { Article } from "../../../types/knowledgeBase";

function article(overrides: Partial<Article> = {}): Article {
  return {
    id: crypto.randomUUID(),
    slug: "reset-password",
    title: "Reset your password",
    summary: "Quick steps",
    body: "Go to settings and click reset.",
    kind: "faq",
    status: "published",
    category_id: null,
    view_count: 3,
    author_agent_id: null,
    published_at: "2026-01-01T00:00:00Z",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    category: null,
    ...overrides,
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

function renderPage(slug: string) {
  return render(
    <MemoryRouter initialEntries={[`/portal/kb/${slug}`]}>
      <Routes>
        <Route path="/portal/kb/:slug" element={<PortalArticlePage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("PortalArticlePage", () => {
  it("renders the article title, summary and body", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(JSON.stringify(article()), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    renderPage("reset-password");

    expect(
      await screen.findByRole("heading", { level: 1, name: "Reset your password" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Quick steps")).toBeInTheDocument();
    expect(screen.getByText("Go to settings and click reset.")).toBeInTheDocument();
  });

  it("handles a 404 for a missing or draft article", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(JSON.stringify({ detail: "article not-found not found" }), {
          status: 404,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    renderPage("not-found");

    expect(
      await screen.findByRole("heading", { level: 1, name: "Article not found" }),
    ).toBeInTheDocument();
  });
});
