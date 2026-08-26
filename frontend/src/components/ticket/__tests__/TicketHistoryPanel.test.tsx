import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import TicketHistoryPanel from "../TicketHistoryPanel";
import type { TicketEvent } from "../../../types/ticket";

const TICKET_ID = "33333333-3333-4333-8333-333333333333";

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

interface Recorded {
  method: string;
  url: string;
  body: unknown;
}

function mockApi(initial: TicketEvent[]) {
  const requests: Recorded[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method ?? "GET").toUpperCase();
    requests.push({ method, url, body: init?.body ? JSON.parse(String(init.body)) : undefined });

    if (method === "GET") {
      return new Response(JSON.stringify({ items: initial, total: initial.length }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    return new Response(JSON.stringify(event({ event_type: "commented", comment: "hi" })), {
      status: 201,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  return requests;
}

describe("TicketHistoryPanel", () => {
  it("renders each event type as its own sentence, newest first", async () => {
    // The backend always returns events newest-first; the mock mirrors that.
    mockApi([
      event({
        event_type: "escalated",
        old_value: "0",
        new_value: "1",
        created_at: "2026-01-03T00:00:00Z",
      }),
      event({
        event_type: "status_changed",
        old_value: "open",
        new_value: "triaged",
        created_at: "2026-01-02T00:00:00Z",
      }),
      event({ event_type: "created", created_at: "2026-01-01T00:00:00Z" }),
    ]);

    render(<TicketHistoryPanel ticketId={TICKET_ID} />);

    const items = await screen.findAllByRole("listitem");
    expect(items).toHaveLength(3);
    // The API already returns newest-first; the panel must render in that order.
    expect(items[0]).toHaveTextContent("Escalated to level 1");
    expect(items[1]).toHaveTextContent("Status changed from open to triaged");
    expect(items[2]).toHaveTextContent("Ticket created");
  });

  it("shows an empty state", async () => {
    mockApi([]);
    render(<TicketHistoryPanel ticketId={TICKET_ID} />);
    expect(await screen.findByText("No history yet.")).toBeInTheDocument();
  });

  it("posts a new comment and refreshes", async () => {
    const requests = mockApi([]);
    const user = userEvent.setup();

    render(<TicketHistoryPanel ticketId={TICKET_ID} />);
    await screen.findByText("No history yet.");

    await user.type(screen.getByLabelText("New comment"), "Called back");
    await user.click(screen.getByRole("button", { name: "Add comment" }));

    await waitFor(() =>
      expect(requests.some((r) => r.method === "POST" && r.url.includes("/events"))).toBe(true),
    );
    const posted = requests.find((r) => r.method === "POST")!;
    expect(posted.body).toEqual({ comment: "Called back", actor: undefined });
  });

  it("renders no edit or delete control for any event", async () => {
    mockApi([event({ event_type: "commented", comment: "note" })]);
    render(<TicketHistoryPanel ticketId={TICKET_ID} />);
    await screen.findByText("Comment added");

    expect(screen.queryByRole("button", { name: /edit/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /delete/i })).not.toBeInTheDocument();
  });
});
