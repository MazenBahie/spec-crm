import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import TicketsListPage from "../TicketsListPage";
import type { Ticket } from "../../types/ticket";

/** Mirrors SEARCH_DEBOUNCE_MS in TicketsListPage. */
const SEARCH_DEBOUNCE_MS = 300;

function ticket(overrides: Partial<Ticket> = {}): Ticket {
  return {
    id: crypto.randomUUID(),
    reference: "TCK-AAAAAAAA",
    customer_id: crypto.randomUUID(),
    category_id: null,
    ai_suggested_category_id: null,
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
    ai_summary: null,
    ai_summary_generated_at: null,
    ...overrides,
  };
}

/** Route GET /agents to an empty list and GET /tickets to the given pages. */
function mockFetch(pages: Array<{ items: Ticket[]; total: number }>) {
  const calls: string[] = [];
  let index = 0;
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("/agents")) {
      return new Response(JSON.stringify([]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    calls.push(url);
    const page = pages[Math.min(index, pages.length - 1)];
    index += 1;
    return new Response(JSON.stringify(page), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  return { calls, fetchMock };
}

function renderPage() {
  return render(
    <MemoryRouter>
      <TicketsListPage />
    </MemoryRouter>,
  );
}

describe("TicketsListPage", () => {
  beforeEach(() => {
    vi.useRealTimers();
  });

  it("renders rows from the fetched page", async () => {
    mockFetch([
      { items: [ticket({ subject: "Alpha issue" }), ticket({ subject: "Beta issue", status: "triaged" })], total: 2 },
    ]);

    renderPage();

    expect(await screen.findByText("Alpha issue")).toBeInTheDocument();
    expect(screen.getByText("Beta issue")).toBeInTheDocument();
    expect(screen.getByText(/2 ticket\(s\) match/)).toBeInTheDocument();
  });

  it("links each row to the ticket detail route", async () => {
    const row = ticket({ subject: "Linkable" });
    mockFetch([{ items: [row], total: 1 }]);

    renderPage();

    const link = await screen.findByRole("link", { name: row.reference });
    expect(link).toHaveAttribute("href", `/tickets/${row.id}`);
  });

  it("shows an empty state when there are no tickets", async () => {
    mockFetch([{ items: [], total: 0 }]);
    renderPage();
    expect(await screen.findByText(/No tickets match/)).toBeInTheDocument();
  });

  it("surfaces an API error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        if (String(input).includes("/agents")) {
          return new Response(JSON.stringify([]), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        return new Response(JSON.stringify({ detail: "boom" }), {
          status: 500,
          headers: { "Content-Type": "application/json" },
        });
      }),
    );

    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent("boom");
  });

  it("debounces search so typing does not fire a request per keystroke", async () => {
    const { calls } = mockFetch([{ items: [], total: 0 }]);
    const user = userEvent.setup();

    renderPage();
    await waitFor(() => expect(calls.length).toBe(1));

    await user.type(screen.getByLabelText("Search tickets"), "pass");

    await waitFor(() => expect(calls.some((url) => url.includes("q=pass"))).toBe(true));
    expect(calls.filter((url) => url.includes("q=")).length).toBe(1);
    expect(calls.length).toBe(2);
  });

  it("sends status/priority/unassigned filters and resets to the first page", async () => {
    const { calls } = mockFetch([{ items: [], total: 0 }]);
    const user = userEvent.setup();

    renderPage();
    await waitFor(() => expect(calls.length).toBe(1));

    await user.selectOptions(screen.getByLabelText("Filter by status"), "triaged");
    await waitFor(() => expect(calls.at(-1)).toContain("status=triaged"));

    await user.selectOptions(screen.getByLabelText("Filter by priority"), "high");
    await waitFor(() => expect(calls.at(-1)).toContain("priority=high"));

    await user.click(screen.getByLabelText("Unassigned only"));
    await waitFor(() => expect(calls.at(-1)).toContain("unassigned=true"));
    expect(calls.at(-1)).toContain("offset=0");
  });

  it("advances pagination and disables the controls at the edges", async () => {
    const many = Array.from({ length: 20 }, (_, i) => ticket({ subject: `Ticket ${i}` }));
    const { calls } = mockFetch([
      { items: many, total: 25 },
      { items: [ticket({ subject: "Page two row" })], total: 25 },
    ]);
    const user = userEvent.setup();

    renderPage();
    await screen.findByText("Ticket 0");

    expect(screen.getByText("Page 1 of 2")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();

    // Let the search debounce armed on mount fire before paging. It resets
    // `offset` to 0, so a click landing inside that 300ms window is undone a
    // moment later — on a loaded machine this would fail intermittently.
    await new Promise((resolve) => setTimeout(resolve, SEARCH_DEBOUNCE_MS + 50));

    await user.click(screen.getByRole("button", { name: "Next" }));

    expect(await screen.findByText("Page two row")).toBeInTheDocument();
    expect(calls.at(-1)).toContain("offset=20");
    await waitFor(() => expect(screen.getByRole("button", { name: "Next" })).toBeDisabled());
  });

  it("offers links to create a ticket and to setup", async () => {
    mockFetch([{ items: [], total: 0 }]);
    renderPage();
    expect(await screen.findByRole("link", { name: "New ticket" })).toHaveAttribute(
      "href",
      "/tickets/new",
    );
    expect(screen.getByRole("link", { name: "Setup" })).toHaveAttribute("href", "/tickets/setup");
  });

  it("renders the table header", async () => {
    mockFetch([{ items: [ticket()], total: 1 }]);
    renderPage();
    const table = await screen.findByRole("table");
    const headers = within(table).getAllByRole("columnheader");
    expect(headers.map((h) => h.textContent)).toEqual([
      "Reference",
      "Subject",
      "Priority",
      "Status",
      "Assignee",
      "Updated",
    ]);
  });

  it("marks an overdue ticket in the row", async () => {
    mockFetch([{ items: [ticket({ subject: "Late one", is_overdue: true })], total: 1 }]);
    renderPage();
    await screen.findByText("Late one");
    expect(screen.getByText("overdue")).toBeInTheDocument();
  });
});
