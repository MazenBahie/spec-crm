import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import SuggestedSolutionsPanel from "../SuggestedSolutionsPanel";
import type { ArticleSummary } from "../../../types/knowledgeBase";

const TICKET_ID = "66666666-6666-4666-8666-666666666666";

function article(overrides: Partial<ArticleSummary> = {}): ArticleSummary {
  return {
    id: crypto.randomUUID(),
    slug: "reset-password",
    title: "How to reset your password",
    summary: "Step by step reset instructions.",
    kind: "help",
    status: "published",
    category_id: null,
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function mockFetch(response: ArticleSummary[] | { status: number }) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => {
      if ("status" in response) {
        return new Response(JSON.stringify({ detail: "boom" }), { status: response.status });
      }
      return new Response(JSON.stringify(response), { status: 200 });
    }),
  );
}

function renderPanel() {
  return render(
    <MemoryRouter>
      <SuggestedSolutionsPanel ticketId={TICKET_ID} />
    </MemoryRouter>,
  );
}

describe("SuggestedSolutionsPanel", () => {
  it("renders a list of suggested articles linking to /kb/:id", async () => {
    const a = article();
    mockFetch([a]);
    renderPanel();

    const link = await screen.findByRole("link", { name: a.title });
    expect(link).toHaveAttribute("href", `/kb/${a.id}`);
  });

  it("renders the empty-state sentence when there are no matches", async () => {
    mockFetch([]);
    renderPanel();
    expect(await screen.findByText("No matching knowledge base articles found.")).toBeInTheDocument();
  });

  it("renders an ErrorBanner instead of crashing on failure", async () => {
    mockFetch({ status: 500 });
    renderPanel();
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });

  it("shows a visible AI label on the panel header", async () => {
    mockFetch([]);
    renderPanel();
    await screen.findByText("No matching knowledge base articles found.");
    expect(screen.getByText("AI")).toBeInTheDocument();
  });
});
