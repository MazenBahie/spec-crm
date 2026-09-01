import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import PortalTicketDetailPage from "../PortalTicketDetailPage";
import type { Ticket, TicketEvent } from "../../../types/ticket";

const TICKET_ID = "22222222-2222-4222-8222-222222222222";

function ticket(overrides: Partial<Ticket> = {}): Ticket {
  return {
    id: TICKET_ID,
    reference: "TCK-AAAAAAAA",
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
    ...overrides,
  };
}

function event(overrides: Partial<TicketEvent> = {}): TicketEvent {
  return {
    id: crypto.randomUUID(),
    ticket_id: TICKET_ID,
    event_type: "created",
    field: null,
    old_value: null,
    new_value: null,
    comment: null,
    actor: null,
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function mockFetch(opts: {
  ticket: Ticket;
  events: TicketEvent[];
  feedback?: unknown;
}) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = (init?.method ?? "GET").toUpperCase();
      if (url.endsWith("/events")) {
        return new Response(JSON.stringify(opts.events), { status: 200 });
      }
      if (url.endsWith("/feedback") && method === "GET") {
        return new Response(JSON.stringify(opts.feedback ?? null), { status: 200 });
      }
      if (url.endsWith("/feedback") && method === "POST") {
        const body = JSON.parse(String(init?.body));
        return new Response(
          JSON.stringify({
            id: "feedback-1",
            ticket_id: TICKET_ID,
            rating: body.rating,
            comment: body.comment,
            created_at: "2026-01-03T00:00:00Z",
            updated_at: "2026-01-03T00:00:00Z",
          }),
          { status: 200 },
        );
      }
      return new Response(JSON.stringify(opts.ticket), { status: 200 });
    }),
  );
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={[`/portal/tickets/${TICKET_ID}`]}>
      <Routes>
        <Route path="/portal/tickets/:id" element={<PortalTicketDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("PortalTicketDetailPage", () => {
  it("hides the feedback form for a non-terminal ticket", async () => {
    mockFetch({ ticket: ticket({ status: "open" }), events: [event()] });
    renderPage();

    await screen.findByText("Cannot log in");
    expect(screen.queryByText("How did we do?")).not.toBeInTheDocument();
  });

  it("shows the feedback form for a resolved ticket and saves a submission", async () => {
    mockFetch({ ticket: ticket({ status: "resolved" }), events: [event()] });
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("How did we do?");
    await user.click(screen.getByRole("button", { name: "Submit feedback" }));

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Update feedback" })).toBeInTheDocument(),
    );
  });

  it("renders only created and status_changed events, even if others are returned", async () => {
    mockFetch({
      ticket: ticket({ status: "open" }),
      events: [
        event({ id: "1", event_type: "created" }),
        event({ id: "2", event_type: "status_changed", old_value: "open", new_value: "triaged" }),
        event({ id: "3", event_type: "assigned" }),
        event({ id: "4", event_type: "priority_changed" }),
        event({ id: "5", event_type: "escalated" }),
      ],
    });
    renderPage();

    expect(await screen.findByText("Ticket created.")).toBeInTheDocument();
    expect(
      await screen.findByText("Status changed from open to triaged."),
    ).toBeInTheDocument();
    expect(screen.queryByText(/assigned/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/priority_changed/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/escalated/i)).not.toBeInTheDocument();
  });
});
