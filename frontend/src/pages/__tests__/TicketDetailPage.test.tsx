import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import TicketDetailPage from "../TicketDetailPage";
import type { TicketDetail } from "../../types/ticket";

const TICKET_ID = "33333333-3333-4333-8333-333333333333";

function ticketDetail(overrides: Partial<TicketDetail> = {}): TicketDetail {
  return {
    id: TICKET_ID,
    reference: "TCK-33333333",
    customer_id: crypto.randomUUID(),
    category_id: null,
    ai_suggested_category_id: null,
    assignee_id: null,
    subject: "Cannot log in",
    description: "Details here",
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
    ai_summary: null,
    ai_summary_generated_at: null,
    customer: { id: crypto.randomUUID(), display_name: "Ali Hassan", company: null, status: "active" },
    category: null,
    ai_suggested_category: null,
    assignee: null,
    ...overrides,
  };
}

function mockApi(ticket: TicketDetail, opts: { regenerated?: TicketDetail; regenerateStatus?: number } = {}) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method ?? "GET").toUpperCase();
    const json = (payload: unknown, status = 200) =>
      new Response(JSON.stringify(payload), { status, headers: { "Content-Type": "application/json" } });

    if (url.includes("/ai/summary") && method === "POST") {
      if (opts.regenerateStatus && opts.regenerateStatus >= 400) {
        return json({ detail: "AI provider unavailable" }, opts.regenerateStatus);
      }
      return json(opts.regenerated ?? ticket);
    }
    if (url.includes("/events")) return json({ items: [], total: 0 });
    if (url.includes("/messages")) return json({ items: [], total: 0 });
    if (url.includes("/channels")) return json([]);
    if (url.includes("/notes")) return json({ items: [], total: 0 });
    if (url.includes("/ticket-categories")) return json([]);
    if (url.includes("/ai/suggested-solutions")) return json([]);
    return json(ticket);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={[`/tickets/${TICKET_ID}`]}>
      <Routes>
        <Route path="/tickets/:id" element={<TicketDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("TicketDetailPage AI summary panel", () => {
  it("shows 'No summary yet.' and a Generate summary button when unset", async () => {
    mockApi(ticketDetail());
    renderPage();

    await screen.findByText("No summary yet.");
    expect(screen.getByRole("button", { name: "Generate summary" })).toBeInTheDocument();
    expect(screen.getByText("AI-generated")).toBeInTheDocument();
  });

  it("regenerating populates the summary and switches the button label", async () => {
    const user = userEvent.setup();
    mockApi(ticketDetail(), {
      regenerated: ticketDetail({
        ai_summary: "Customer cannot log in; password reset pending.",
        ai_summary_generated_at: "2026-01-03T00:00:00Z",
      }),
    });
    renderPage();

    await screen.findByText("No summary yet.");
    await user.click(screen.getByRole("button", { name: "Generate summary" }));

    await screen.findByText("Customer cannot log in; password reset pending.");
    expect(screen.getByRole("button", { name: "Regenerate" })).toBeInTheDocument();
  });

  it("shows an inline error on failure without crashing the rest of the page", async () => {
    const user = userEvent.setup();
    mockApi(ticketDetail(), { regenerateStatus: 502 });
    renderPage();

    await screen.findByText("No summary yet.");
    await user.click(screen.getByRole("button", { name: "Generate summary" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("AI provider unavailable");
    // The rest of the page still renders/works.
    expect(screen.getByRole("tab", { name: "Messages" })).toBeInTheDocument();
    expect(screen.getByText("No summary yet.")).toBeInTheDocument();
  });
});
