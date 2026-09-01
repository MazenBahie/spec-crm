import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import DashboardPage from "../DashboardPage";
import { clearAgentId, setAgentId } from "../../api/agentContext";
import type { Ticket } from "../../types/ticket";

const AGENT_ID = "11111111-1111-4111-8111-111111111111";
const OTHER_ID = "22222222-2222-4222-8222-222222222222";

const AGENTS = [
  { id: AGENT_ID, display_name: "Dana Support", email: "dana@crm.test", is_active: true },
  { id: OTHER_ID, display_name: "Omar Night", email: "omar@crm.test", is_active: true },
];

function ticket(overrides: Partial<Ticket> = {}): Ticket {
  return {
    id: crypto.randomUUID(),
    reference: "TCK-ABCD1234",
    customer_id: crypto.randomUUID(),
    category_id: null,
    ai_suggested_category_id: null,
    assignee_id: AGENT_ID,
    subject: "Cannot log in",
    description: "",
    status: "open",
    priority: "urgent",
    escalation_level: 0,
    escalated_at: null,
    due_at: null,
    resolved_at: null,
    closed_at: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    is_overdue: false,
    ai_summary: null,
    ai_summary_generated_at: null,
    ...overrides,
  };
}

interface Backend {
  summary?: Record<string, number>;
  queue?: Ticket[];
  customers?: unknown[];
  activity?: unknown[];
  tasks?: unknown[];
}

function mockApi(backend: Backend = {}) {
  const calls: string[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    calls.push(url);
    const json = (payload: unknown) =>
      new Response(JSON.stringify(payload), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });

    if (url.includes("/dashboard/summary")) {
      return json(
        backend.summary ?? {
          open_assigned: 0,
          overdue: 0,
          tasks_due_today: 0,
          unread_mentions: 0,
        },
      );
    }
    if (url.includes("/dashboard/queue")) return json(backend.queue ?? []);
    if (url.includes("/dashboard/recent-customers")) return json(backend.customers ?? []);
    if (url.includes("/dashboard/activity")) return json(backend.activity ?? []);
    if (url.includes("/tasks")) return json(backend.tasks ?? []);
    if (url.includes("/quick-replies")) return json([]);
    if (url.includes("/agents")) return json(AGENTS);
    return json({ items: [], total: 0 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return calls;
}

function renderPage() {
  return render(
    <MemoryRouter>
      <DashboardPage />
    </MemoryRouter>,
  );
}

/**
 * Wait until every panel has finished its own load.
 *
 * The page is several independently-fetching panels, so asserting on the first
 * one to arrive would leave the others updating state after the test ended.
 * Each renders `Loading…` until it settles, so "none left" is the signal.
 */
async function settle() {
  await waitFor(() => expect(screen.queryAllByText("Loading…")).toHaveLength(0));
}

/** The fake-timer equivalent of `settle`: drain pending promises inside `act`.
 * RTL's `waitFor` cannot be used here — it does not drive vitest's fake
 * timers, so it would simply hang. */
async function flush() {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(0);
  });
}

beforeEach(() => {
  // Set before mounting, never torn down after: the agent id is an external
  // store, so changing it while a component is still subscribed would be a
  // state update outside `act`.
  setAgentId(AGENT_ID);
});

afterEach(() => {
  cleanup();
  clearAgentId();
});

describe("DashboardPage", () => {
  it("renders the summary strip from the API", async () => {
    mockApi({
      summary: { open_assigned: 7, overdue: 2, tasks_due_today: 3, unread_mentions: 1 },
    });
    renderPage();
    await settle();

    for (const [label, value] of [
      ["Open assigned", "7"],
      ["Overdue", "2"],
      ["Tasks due today", "3"],
      ["Unread mentions", "1"],
    ]) {
      const tile = screen.getByText(label).parentElement!;
      expect(tile).toHaveTextContent(value);
    }
  });

  it("renders the queue table with an overdue marker", async () => {
    mockApi({
      queue: [
        ticket({ reference: "TCK-00000001", subject: "Refund please" }),
        ticket({
          reference: "TCK-00000002",
          subject: "Late one",
          due_at: "2026-01-01T00:00:00Z",
          is_overdue: true,
        }),
      ],
    });
    renderPage();
    await settle();

    expect(screen.getByRole("link", { name: "TCK-00000001" })).toHaveAttribute(
      "href",
      expect.stringContaining("/tickets/"),
    );
    expect(screen.getByText("Refund please")).toBeInTheDocument();
    expect(screen.getByText(/overdue/)).toBeInTheDocument();
  });

  it("shows the all-clear empty state for an empty queue", async () => {
    mockApi();
    renderPage();
    await settle();

    expect(screen.getByText("You’re all clear.")).toBeInTheDocument();
  });

  it("shows an empty state for every panel rather than a spinner", async () => {
    mockApi();
    renderPage();
    await settle();

    expect(screen.getByText("You’re all clear.")).toBeInTheDocument();
    expect(
      screen.getByText("Nobody yet — customers you work with will show up here."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("No tasks yet. Add the first one above."),
    ).toBeInTheDocument();
    expect(screen.getByText("Nothing has happened on your tickets yet.")).toBeInTheDocument();
    expect(screen.queryByText("Loading…")).not.toBeInTheDocument();
  });

  it("humanises activity events with the actor's name", async () => {
    mockApi({
      activity: [
        {
          id: crypto.randomUUID(),
          event_type: "note.added",
          agent_id: OTHER_ID,
          ticket_id: "abc",
          customer_id: null,
          payload: { reference: "TCK-00000009" },
          mentions: [AGENT_ID],
          created_at: "2026-01-02T00:00:00Z",
        },
      ],
    });
    renderPage();
    await settle();

    expect(
      screen.getByText("Omar Night added an internal note on TCK-00000009"),
    ).toBeInTheDocument();
  });

  it("polls the summary and activity every 30 seconds", async () => {
    vi.useFakeTimers();
    try {
      const calls = mockApi();
      renderPage();
      await flush();

      expect(calls.filter((u) => u.includes("/dashboard/summary"))).toHaveLength(1);
      // The queue is loaded once, not on every tick.
      const queueCallsBefore = calls.filter((u) => u.includes("/dashboard/queue")).length;

      await act(async () => {
        await vi.advanceTimersByTimeAsync(30_000);
      });

      expect(
        calls.filter((u) => u.includes("/dashboard/summary")).length,
      ).toBeGreaterThan(1);
      expect(calls.filter((u) => u.includes("/dashboard/queue"))).toHaveLength(
        queueCallsBefore,
      );
    } finally {
      vi.useRealTimers();
    }
  });

  it("skips the poll while the tab is hidden", async () => {
    vi.useFakeTimers();
    try {
      const calls = mockApi();
      renderPage();
      await flush();

      vi.spyOn(document, "visibilityState", "get").mockReturnValue("hidden");
      await act(async () => {
        await vi.advanceTimersByTimeAsync(90_000);
      });

      expect(calls.filter((u) => u.includes("/dashboard/summary"))).toHaveLength(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it("stops polling once unmounted", async () => {
    vi.useFakeTimers();
    try {
      const calls = mockApi();
      const { unmount } = renderPage();
      await flush();

      unmount();
      await act(async () => {
        await vi.advanceTimersByTimeAsync(120_000);
      });

      expect(calls.filter((u) => u.includes("/dashboard/summary"))).toHaveLength(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it("sends the agent id on dashboard requests", async () => {
    mockApi();
    renderPage();
    await settle();

    const [, init] = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.find(
      ([url]) => String(url).includes("/dashboard/summary"),
    )!;
    expect((init as RequestInit).headers).toMatchObject({ "X-Agent-Id": AGENT_ID });
  });

  it("falls back to the agent picker when the id is rejected", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/agents")) {
          return new Response(JSON.stringify(AGENTS), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        // What the backend answers for a deleted or deactivated agent.
        return new Response(JSON.stringify({ detail: "a valid X-Agent-Id header is required" }), {
          status: 401,
          headers: { "Content-Type": "application/json" },
        });
      }),
    );
    renderPage();

    expect(
      await screen.findByRole("heading", { level: 1, name: "Who is on shift?" }),
    ).toBeInTheDocument();
  });
});
