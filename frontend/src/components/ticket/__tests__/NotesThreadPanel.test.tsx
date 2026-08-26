import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import NotesThreadPanel from "../NotesThreadPanel";
import type { TicketNote } from "../../../types/agent";

const TICKET_ID = "44444444-4444-4444-8444-444444444444";
const AGENT_ID = "11111111-1111-4111-8111-111111111111";
const OTHER_ID = "22222222-2222-4222-8222-222222222222";

const AGENTS = [
  { id: AGENT_ID, display_name: "Dana Support", email: "dana@crm.test", is_active: true },
  { id: OTHER_ID, display_name: "Omar Night", email: "omar@crm.test", is_active: true },
];

function note(overrides: Partial<TicketNote> = {}): TicketNote {
  return {
    id: crypto.randomUUID(),
    ticket_id: TICKET_ID,
    author_agent_id: AGENT_ID,
    author_display_name: "Dana Support",
    body: "Billing looks wrong here.",
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

interface Recorded {
  method: string;
  url: string;
  body: unknown;
}

function mockApi(thread: TicketNote[], options: { created?: TicketNote } = {}) {
  const requests: Recorded[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = (init?.method ?? "GET").toUpperCase();
      requests.push({
        method,
        url,
        body: init?.body ? JSON.parse(String(init.body)) : undefined,
      });

      const json = (payload: unknown, status = 200) =>
        new Response(JSON.stringify(payload), {
          status,
          headers: { "Content-Type": "application/json" },
        });

      if (url.includes("/agents")) return json(AGENTS);
      if (method === "POST") {
        const created = options.created ?? note({ body: String((JSON.parse(String(init!.body)) as { body: string }).body) });
        thread.push(created);
        return json(created, 201);
      }
      return json({ items: thread, total: thread.length });
    }),
  );
  return requests;
}

describe("NotesThreadPanel", () => {
  it("renders the thread oldest-first with its authors", async () => {
    mockApi([
      note({ body: "first", author_display_name: "Dana Support" }),
      note({
        body: "second",
        author_display_name: "Omar Night",
        created_at: "2026-01-02T00:00:00Z",
      }),
    ]);

    render(<NotesThreadPanel ticketId={TICKET_ID} />);

    const items = await screen.findAllByRole("listitem");
    expect(items[0]).toHaveTextContent("Dana Support");
    expect(items[0]).toHaveTextContent("first");
    expect(items[1]).toHaveTextContent("Omar Night");
    expect(items[1]).toHaveTextContent("second");
  });

  it("says these notes never reach the customer", async () => {
    mockApi([]);
    render(<NotesThreadPanel ticketId={TICKET_ID} />);

    expect(
      await screen.findByText("Only your team sees these. They are never sent to the customer."),
    ).toBeInTheDocument();
  });

  it("shows an empty state", async () => {
    mockApi([]);
    render(<NotesThreadPanel ticketId={TICKET_ID} />);

    expect(
      await screen.findByText("No internal notes on this ticket yet."),
    ).toBeInTheDocument();
  });

  it("posts a note and renders it without a refetch", async () => {
    const requests = mockApi([]);
    const user = userEvent.setup();

    render(<NotesThreadPanel ticketId={TICKET_ID} />);
    await screen.findByText("No internal notes on this ticket yet.");

    await user.type(screen.getByLabelText("Note body"), "check the invoice");
    await user.click(screen.getByRole("button", { name: "Post note" }));

    expect(await screen.findByText("check the invoice")).toBeInTheDocument();
    const posted = requests.find((r) => r.method === "POST")!;
    expect(posted.url).toContain(`/tickets/${TICKET_ID}/notes`);
    expect(posted.body).toEqual({ body: "check the invoice" });
    // Composer cleared, ready for the next one.
    expect(screen.getByLabelText("Note body")).toHaveValue("");
  });

  it("highlights an @mention in a posted note", async () => {
    mockApi([note({ body: "@omar can you take a look?" })]);

    render(<NotesThreadPanel ticketId={TICKET_ID} />);

    const item = await screen.findByRole("listitem");
    const mention = within(item).getByText("@omar");
    expect(mention.tagName).toBe("MARK");
    // The surrounding prose is not swept into the highlight.
    expect(item).toHaveTextContent("@omar can you take a look?");
  });

  it("highlights every mention in a note", async () => {
    mockApi([note({ body: "@omar and @dana please sync" })]);

    render(<NotesThreadPanel ticketId={TICKET_ID} />);

    const item = await screen.findByRole("listitem");
    expect(within(item).getByText("@omar").tagName).toBe("MARK");
    expect(within(item).getByText("@dana").tagName).toBe("MARK");
  });

  it("suggests teammates after typing @ and completes the handle", async () => {
    mockApi([]);
    const user = userEvent.setup();

    render(<NotesThreadPanel ticketId={TICKET_ID} />);
    await screen.findByText("No internal notes on this ticket yet.");

    await user.type(screen.getByLabelText("Note body"), "cc @om");

    const suggestions = await screen.findByLabelText("Mention suggestions");
    const button = within(suggestions).getByRole("button", { name: "@omar" });
    await user.click(button);

    expect(screen.getByLabelText("Note body")).toHaveValue("cc @omar ");
  });

  it("will not post an empty or whitespace-only note", async () => {
    const requests = mockApi([]);
    const user = userEvent.setup();

    render(<NotesThreadPanel ticketId={TICKET_ID} />);
    await screen.findByText("No internal notes on this ticket yet.");

    expect(screen.getByRole("button", { name: "Post note" })).toBeDisabled();
    await user.type(screen.getByLabelText("Note body"), "   ");
    expect(screen.getByRole("button", { name: "Post note" })).toBeDisabled();
    expect(requests.some((r) => r.method === "POST")).toBe(false);
  });

  it("names an author the backend could not resolve", async () => {
    mockApi([note({ author_agent_id: null, author_display_name: null })]);

    render(<NotesThreadPanel ticketId={TICKET_ID} />);

    expect(await screen.findByText("Unknown agent")).toBeInTheDocument();
  });

  it("surfaces an API error from the initial load", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(JSON.stringify({ detail: "a valid X-Agent-Id header is required" }), {
            status: 401,
            headers: { "Content-Type": "application/json" },
          }),
      ),
    );

    render(<NotesThreadPanel ticketId={TICKET_ID} />);

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent("X-Agent-Id"),
    );
  });
});
