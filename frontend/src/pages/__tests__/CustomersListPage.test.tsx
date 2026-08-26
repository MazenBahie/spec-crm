import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import CustomersListPage from "../CustomersListPage";
import type { Customer } from "../../types/customer";

/** Mirrors SEARCH_DEBOUNCE_MS in CustomersListPage. */
const SEARCH_DEBOUNCE_MS = 300;

function customer(overrides: Partial<Customer> = {}): Customer {
  return {
    id: crypto.randomUUID(),
    display_name: "Acme Corp",
    company: "Acme",
    status: "active",
    archived_at: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-02T00:00:00Z",
    ...overrides,
  };
}

/** Capture every request URL so we can assert on query params. */
function mockFetch(pages: Array<{ items: Customer[]; total: number }>) {
  const calls: string[] = [];
  let index = 0;
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    calls.push(String(input));
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
      <CustomersListPage />
    </MemoryRouter>,
  );
}

describe("CustomersListPage", () => {
  beforeEach(() => {
    vi.useRealTimers();
  });

  it("renders rows from the fetched page", async () => {
    mockFetch([
      {
        items: [
          customer({ display_name: "Alpha Ltd", company: "Alpha" }),
          customer({ display_name: "Beta GmbH", company: null, status: "archived" }),
        ],
        total: 2,
      },
    ]);

    renderPage();

    expect(await screen.findByText("Alpha Ltd")).toBeInTheDocument();
    expect(screen.getByText("Beta GmbH")).toBeInTheDocument();
    // Missing company renders as an em dash rather than "null".
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.getByText("archived")).toBeInTheDocument();
    expect(screen.getByText(/2 customer\(s\) match/)).toBeInTheDocument();
  });

  it("links each row to the customer detail route", async () => {
    const row = customer({ display_name: "Linkable" });
    mockFetch([{ items: [row], total: 1 }]);

    renderPage();

    const link = await screen.findByRole("link", { name: "Linkable" });
    expect(link).toHaveAttribute("href", `/customers/${row.id}`);
  });

  it("shows an empty state when there are no customers", async () => {
    mockFetch([{ items: [], total: 0 }]);
    renderPage();
    expect(await screen.findByText(/No customers yet/)).toBeInTheDocument();
  });

  it("surfaces an API error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(JSON.stringify({ detail: "boom" }), {
            status: 500,
            headers: { "Content-Type": "application/json" },
          }),
      ),
    );

    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent("boom");
  });

  it("debounces search so typing does not fire a request per keystroke", async () => {
    const { calls } = mockFetch([{ items: [], total: 0 }]);
    const user = userEvent.setup();

    renderPage();
    await waitFor(() => expect(calls.length).toBe(1));

    await user.type(screen.getByLabelText("Search customers"), "acme");

    // Four keystrokes must not produce four requests.
    await waitFor(() => expect(calls.some((url) => url.includes("q=acme"))).toBe(true));
    expect(calls.filter((url) => url.includes("q=")).length).toBe(1);
    expect(calls.length).toBe(2);
  });

  it("sends the status filter and resets to the first page", async () => {
    const { calls } = mockFetch([{ items: [], total: 0 }]);
    const user = userEvent.setup();

    renderPage();
    await waitFor(() => expect(calls.length).toBe(1));

    await user.selectOptions(screen.getByLabelText("Filter by status"), "archived");

    await waitFor(() => expect(calls.at(-1)).toContain("status=archived"));
    expect(calls.at(-1)).toContain("offset=0");
  });

  it("advances pagination and disables the controls at the edges", async () => {
    const many = Array.from({ length: 20 }, (_, i) =>
      customer({ display_name: `Customer ${i}` }),
    );
    const { calls } = mockFetch([
      { items: many, total: 25 },
      { items: [customer({ display_name: "Page two row" })], total: 25 },
    ]);
    const user = userEvent.setup();

    renderPage();
    await screen.findByText("Customer 0");

    expect(screen.getByText("Page 1 of 2")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();

    // Let the search debounce that was armed on mount fire before paging. It
    // resets `offset` to 0, so a click landing inside that 300ms window is
    // undone a moment later — on a loaded machine, this test would otherwise
    // fail intermittently.
    await new Promise((resolve) => setTimeout(resolve, SEARCH_DEBOUNCE_MS + 50));

    await user.click(screen.getByRole("button", { name: "Next" }));

    expect(await screen.findByText("Page two row")).toBeInTheDocument();
    expect(calls.at(-1)).toContain("offset=20");
    expect(screen.getByText("Page 2 of 2")).toBeInTheDocument();
    // Last page: Next is disabled again.
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Next" })).toBeDisabled(),
    );
  });

  it("requests the default page size", async () => {
    const { calls } = mockFetch([{ items: [], total: 0 }]);
    renderPage();
    await waitFor(() => expect(calls[0]).toContain("limit=20"));
    expect(calls[0]).toContain("/api/customers?");
  });

  it("offers a link to create a new customer", async () => {
    mockFetch([{ items: [], total: 0 }]);
    renderPage();
    const link = await screen.findByRole("link", { name: "New customer" });
    expect(link).toHaveAttribute("href", "/customers/new");
  });

  it("renders the table header", async () => {
    mockFetch([{ items: [customer()], total: 1 }]);
    renderPage();
    const table = await screen.findByRole("table");
    const headers = within(table).getAllByRole("columnheader");
    expect(headers.map((h) => h.textContent)).toEqual([
      "Name",
      "Company",
      "Status",
      "Updated",
    ]);
  });
});
