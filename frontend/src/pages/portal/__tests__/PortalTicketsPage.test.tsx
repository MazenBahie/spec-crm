import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import PortalTicketsPage from "../PortalTicketsPage";
import type { Ticket } from "../../../types/ticket";

function ticket(overrides: Partial<Ticket> = {}): Ticket {
  return {
    id: crypto.randomUUID(),
    reference: "TCK-AAAAAAAA",
    customer_id: crypto.randomUUID(),
    category_id: null,
    assignee_id: null,
    subject: "Cannot log in",
    description: "",
    status: "open",
    priority: "normal",
    escalation_level: 0,
    escalated_at: null,
    due_at: null,
    resolved_at: null,
    closed_at: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-02T00:00:00Z",
    is_overdue: false,
    ...overrides,
  };
}

function mockFetch(page: { items: Ticket[]; total: number }) {
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        new Response(JSON.stringify(page), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
    ),
  );
}

function renderPage() {
  return render(
    <MemoryRouter>
      <PortalTicketsPage />
    </MemoryRouter>,
  );
}

describe("PortalTicketsPage", () => {
  it("renders rows linking to the ticket detail page", async () => {
    const t = ticket({ subject: "Cannot log in" });
    mockFetch({ items: [t], total: 1 });
    renderPage();

    const link = await screen.findByRole("link", { name: t.reference });
    expect(link).toHaveAttribute("href", `/portal/tickets/${t.id}`);
    expect(screen.getByText("Cannot log in")).toBeInTheDocument();
  });

  it("shows an empty state when there are no tickets", async () => {
    mockFetch({ items: [], total: 0 });
    renderPage();

    expect(
      await screen.findByText("You have not submitted any tickets yet."),
    ).toBeInTheDocument();
  });

  it("disables Previous on the first page and Next on the last page", async () => {
    mockFetch({ items: [ticket()], total: 1 });
    renderPage();

    await screen.findByRole("link", { name: /TCK-/ });
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
  });
});
