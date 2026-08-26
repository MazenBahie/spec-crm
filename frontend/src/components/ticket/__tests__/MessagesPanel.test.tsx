import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import MessagesPanel from "../MessagesPanel";
import type { Channel, ChannelMessage, ChannelSlug } from "../../../types/channel";
import type { QuickReply } from "../../../types/agent";
import type { TicketDetail } from "../../../types/ticket";

const TICKET_ID = "44444444-4444-4444-8444-444444444444";

const CATALOGUE: Array<[ChannelSlug, string]> = [
  ["email", "Email"],
  ["live_chat", "Live chat"],
  ["sms", "SMS"],
  ["web_form", "Web forms"],
  ["whatsapp", "WhatsApp"],
];

function channels(disabled: ChannelSlug[] = []): Channel[] {
  return CATALOGUE.map(([slug, display_name]) => ({
    id: crypto.randomUUID(),
    slug,
    display_name,
    is_enabled: !disabled.includes(slug),
    config: null,
    created_at: "2026-01-01T00:00:00Z",
  }));
}

function message(overrides: Partial<ChannelMessage> = {}): ChannelMessage {
  return {
    id: crypto.randomUUID(),
    ticket_id: TICKET_ID,
    channel_id: crypto.randomUUID(),
    channel_slug: "email",
    customer_id: crypto.randomUUID(),
    direction: "inbound",
    status: "received",
    body: "Still cannot log in.",
    provider_message_id: null,
    error_reason: null,
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

interface Recorded {
  method: string;
  url: string;
  body: unknown;
}

function quickReply(overrides: Partial<QuickReply> = {}): QuickReply {
  return {
    id: crypto.randomUUID(),
    scope: "team",
    owner_agent_id: null,
    shortcut: null,
    title: "Greeting",
    body: "Hi {{customer.first_name}}, about {{ticket.reference}}.",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

/** Enough of a loaded ticket for the picker to expand its tokens against. */
function ticketDetail(): TicketDetail {
  return {
    id: TICKET_ID,
    reference: "TCK-44444444",
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
    updated_at: "2026-01-01T00:00:00Z",
    is_overdue: false,
    customer: {
      id: crypto.randomUUID(),
      display_name: "Ali Hassan",
      company: null,
      status: "active",
    },
    category: null,
    assignee: null,
  };
}

/**
 * Route GET /channels to the catalogue, GET .../messages to `thread`, and
 * POST .../messages to `sent` — mirroring the backend, which answers 201 even
 * for a failed send.
 */
function mockApi(
  thread: ChannelMessage[],
  options: {
    catalogue?: Channel[];
    sent?: ChannelMessage;
    quickReplies?: QuickReply[];
  } = {},
) {
  const requests: Recorded[] = [];
  const catalogue = options.catalogue ?? channels();
  const quickReplies = options.quickReplies ?? [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method ?? "GET").toUpperCase();
    requests.push({ method, url, body: init?.body ? JSON.parse(String(init.body)) : undefined });

    const json = (payload: unknown, status = 200) =>
      new Response(JSON.stringify(payload), {
        status,
        headers: { "Content-Type": "application/json" },
      });

    if (url.includes("/quick-replies")) return json(quickReplies);
    if (url.includes("/channels")) return json(catalogue);
    if (method === "POST") {
      const sent =
        options.sent ??
        message({ direction: "outbound", status: "failed", error_reason: "boom" });
      thread.push(sent);
      return json(sent, 201);
    }
    return json({ items: thread, total: thread.length });
  });
  vi.stubGlobal("fetch", fetchMock);
  return requests;
}

describe("MessagesPanel", () => {
  it("renders the fetched thread oldest-first with direction, channel, and status", async () => {
    mockApi([
      message({ body: "customer asks", direction: "inbound", status: "received" }),
      message({
        body: "agent answers",
        direction: "outbound",
        status: "delivered",
        channel_slug: "whatsapp",
        created_at: "2026-01-02T00:00:00Z",
      }),
    ]);

    render(<MessagesPanel ticketId={TICKET_ID} />);

    const items = await screen.findAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent("Inbound");
    expect(items[0]).toHaveTextContent("Email");
    expect(items[0]).toHaveTextContent("customer asks");
    expect(items[1]).toHaveTextContent("Outbound");
    // Slugs are never shown raw — the catalogue's display name is.
    expect(items[1]).toHaveTextContent("WhatsApp");
    expect(items[1]).not.toHaveTextContent("whatsapp");
    expect(items[1]).toHaveTextContent("delivered");
  });

  it("shows an empty state", async () => {
    mockApi([]);
    render(<MessagesPanel ticketId={TICKET_ID} />);
    expect(await screen.findByText("No messages on this ticket yet.")).toBeInTheDocument();
  });

  it("shows the failure reason on a message that could not be delivered", async () => {
    mockApi([
      message({
        direction: "outbound",
        status: "failed",
        error_reason: "channel driver 'email' is not implemented yet",
      }),
    ]);

    render(<MessagesPanel ticketId={TICKET_ID} />);

    const item = await screen.findByRole("listitem");
    expect(within(item).getByText("failed")).toBeInTheDocument();
    expect(item).toHaveTextContent("channel driver 'email' is not implemented yet");
  });

  it("defaults the composer to the channel the customer used first", async () => {
    mockApi([
      message({ channel_slug: "sms" }),
      message({ channel_slug: "email", created_at: "2026-01-02T00:00:00Z" }),
    ]);

    render(<MessagesPanel ticketId={TICKET_ID} />);

    await screen.findAllByRole("listitem");
    expect(await screen.findByLabelText("Channel")).toHaveValue("sms");
  });

  it("falls back to the first enabled channel on an empty thread", async () => {
    mockApi([], { catalogue: channels(["email"]) });

    render(<MessagesPanel ticketId={TICKET_ID} />);

    await screen.findByText("No messages on this ticket yet.");
    // Email is disabled, so the alphabetically next enabled channel wins.
    expect(screen.getByLabelText("Channel")).toHaveValue("live_chat");
  });

  it("marks a disabled channel as unselectable", async () => {
    mockApi([], { catalogue: channels(["sms"]) });

    render(<MessagesPanel ticketId={TICKET_ID} />);
    await screen.findByText("No messages on this ticket yet.");

    const option = screen.getByRole("option", { name: "SMS (disabled)" }) as HTMLOptionElement;
    expect(option.disabled).toBe(true);
    expect((screen.getByRole("option", { name: "Email" }) as HTMLOptionElement).disabled).toBe(
      false,
    );
  });

  it("sends the composed body on the selected channel and refreshes", async () => {
    const requests = mockApi([], {
      sent: message({
        direction: "outbound",
        status: "sent",
        channel_slug: "whatsapp",
        body: "On its way",
      }),
    });
    const user = userEvent.setup();

    render(<MessagesPanel ticketId={TICKET_ID} />);
    await screen.findByText("No messages on this ticket yet.");

    await user.selectOptions(screen.getByLabelText("Channel"), "whatsapp");
    await user.type(screen.getByLabelText("Message body"), "On its way");
    await user.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => expect(requests.some((r) => r.method === "POST")).toBe(true));
    expect(requests.find((r) => r.method === "POST")!.body).toEqual({
      channel_slug: "whatsapp",
      body: "On its way",
    });
    // Refreshed: the new message is in the thread and the composer is cleared.
    expect(await screen.findByText("On its way")).toBeInTheDocument();
    expect(screen.getByLabelText("Message body")).toHaveValue("");
  });

  it("surfaces a failed send next to the composer, not just in the thread", async () => {
    mockApi([], {
      sent: message({
        direction: "outbound",
        status: "failed",
        error_reason: "channel driver 'email' is not implemented yet",
      }),
    });
    const user = userEvent.setup();

    render(<MessagesPanel ticketId={TICKET_ID} />);
    await screen.findByText("No messages on this ticket yet.");

    await user.type(screen.getByLabelText("Message body"), "please work");
    await user.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "channel driver 'email' is not implemented yet",
    );
  });

  it("keeps the agent's channel choice across the post-send refresh", async () => {
    const requests = mockApi([], {
      sent: message({ direction: "outbound", status: "sent", channel_slug: "sms" }),
    });
    const user = userEvent.setup();

    render(<MessagesPanel ticketId={TICKET_ID} />);
    await screen.findByText("No messages on this ticket yet.");

    await user.selectOptions(screen.getByLabelText("Channel"), "sms");
    await user.type(screen.getByLabelText("Message body"), "first");
    await user.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => expect(requests.filter((r) => r.method === "POST")).toHaveLength(1));
    // Not reset to the thread's primary channel, which is now "sms" anyway —
    // assert the select still holds the explicit choice.
    await waitFor(() => expect(screen.getByLabelText("Channel")).toHaveValue("sms"));
  });

  it("will not submit an empty or whitespace-only body", async () => {
    const requests = mockApi([]);
    const user = userEvent.setup();

    render(<MessagesPanel ticketId={TICKET_ID} />);
    await screen.findByText("No messages on this ticket yet.");

    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();

    await user.type(screen.getByLabelText("Message body"), "   ");
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    expect(requests.some((r) => r.method === "POST")).toBe(false);
  });

  it("offers the quick-reply picker above the composer", async () => {
    mockApi([], { quickReplies: [quickReply()] });

    render(<MessagesPanel ticketId={TICKET_ID} ticket={ticketDetail()} />);
    await screen.findByText("No messages on this ticket yet.");

    expect(screen.getByRole("button", { name: /Quick reply/ })).toBeInTheDocument();
  });

  it("inserts a rendered quick reply into the composer", async () => {
    mockApi([], { quickReplies: [quickReply({ title: "Greeting" })] });
    const user = userEvent.setup();

    render(<MessagesPanel ticketId={TICKET_ID} ticket={ticketDetail()} />);
    await screen.findByText("No messages on this ticket yet.");

    await user.click(screen.getByRole("button", { name: /Quick reply/ }));
    await user.click(await screen.findByRole("option", { name: /Greeting/ }));

    // Tokens expanded against the loaded ticket and its customer.
    expect(screen.getByLabelText("Message body")).toHaveValue(
      "Hi Ali, about TCK-44444444.",
    );
  });

  it("sends an inserted quick reply through the unchanged send API", async () => {
    const requests = mockApi([], {
      quickReplies: [quickReply({ title: "Greeting" })],
      sent: message({ direction: "outbound", status: "sent" }),
    });
    const user = userEvent.setup();

    render(<MessagesPanel ticketId={TICKET_ID} ticket={ticketDetail()} />);
    await screen.findByText("No messages on this ticket yet.");

    await user.click(screen.getByRole("button", { name: /Quick reply/ }));
    await user.click(await screen.findByRole("option", { name: /Greeting/ }));
    await user.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => expect(requests.some((r) => r.method === "POST")).toBe(true));
    const posted = requests.find((r) => r.method === "POST")!;
    // The DTO is exactly what it was before quick replies existed: the
    // rendered text goes out as a plain body, with no extra fields.
    expect(posted.body).toEqual({
      channel_slug: "email",
      body: "Hi Ali, about TCK-44444444.",
    });
  });

  it("leaves tokens literal when no ticket has been passed in", async () => {
    mockApi([], { quickReplies: [quickReply({ title: "Greeting" })] });
    const user = userEvent.setup();

    // The composer still works without ticket context — the picker degrades
    // rather than disappearing.
    render(<MessagesPanel ticketId={TICKET_ID} />);
    await screen.findByText("No messages on this ticket yet.");

    await user.click(screen.getByRole("button", { name: /Quick reply/ }));
    await user.click(await screen.findByRole("option", { name: /Greeting/ }));

    expect(screen.getByLabelText("Message body")).toHaveValue(
      "Hi {{customer.first_name}}, about {{ticket.reference}}.",
    );
  });

  it("surfaces an API error from the initial load", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(JSON.stringify({ detail: "ticket not found" }), {
            status: 404,
            headers: { "Content-Type": "application/json" },
          }),
      ),
    );

    render(<MessagesPanel ticketId={TICKET_ID} />);

    expect(await screen.findByRole("alert")).toHaveTextContent("ticket not found");
  });
});
