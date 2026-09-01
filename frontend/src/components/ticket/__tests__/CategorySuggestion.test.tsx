import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import CategorySuggestion from "../CategorySuggestion";
import type { TicketCategory, TicketDetail } from "../../../types/ticket";

const TICKET_ID = "55555555-5555-4555-8555-555555555555";

function category(overrides: Partial<TicketCategory> = {}): TicketCategory {
  return {
    id: crypto.randomUUID(),
    name: "Billing",
    description: null,
    default_priority: "normal",
    is_active: true,
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function ticketDetail(overrides: Partial<TicketDetail> = {}): TicketDetail {
  return {
    id: TICKET_ID,
    reference: "TCK-55555555",
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
    updated_at: "2026-01-01T00:00:00Z",
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

function mockApi(opts: { categories?: TicketCategory[] } = {}) {
  const requests: { method: string; url: string; body: unknown }[] = [];
  const categories = opts.categories ?? [category()];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method ?? "GET").toUpperCase();
    requests.push({ method, url, body: init?.body ? JSON.parse(String(init.body)) : undefined });
    const json = (payload: unknown, status = 200) =>
      new Response(JSON.stringify(payload), { status, headers: { "Content-Type": "application/json" } });

    if (url.includes("/ticket-categories")) return json(categories);
    if (url.includes("/ai/suggested-category")) return json(ticketDetail());
    if (method === "PATCH") return json(ticketDetail());
    return json(ticketDetail());
  });
  vi.stubGlobal("fetch", fetchMock);
  return requests;
}

describe("CategorySuggestion", () => {
  it("renders the suggestion with an AI tag and Apply button when it differs from the current category", async () => {
    mockApi();
    const suggested = category({ name: "Technical" });
    render(
      <CategorySuggestion
        ticket={ticketDetail({ ai_suggested_category: suggested })}
        onChanged={vi.fn()}
      />,
    );

    expect(await screen.findByText(/Suggests: Technical/)).toBeInTheDocument();
    expect(screen.getByText("AI")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Apply" })).toBeInTheDocument();
  });

  it("clicking Apply PATCHes the ticket and calls onChanged", async () => {
    const requests = mockApi();
    const onChanged = vi.fn();
    const suggested = category({ name: "Technical" });
    const user = userEvent.setup();

    render(
      <CategorySuggestion
        ticket={ticketDetail({ ai_suggested_category: suggested })}
        onChanged={onChanged}
      />,
    );

    await user.click(await screen.findByRole("button", { name: "Apply" }));

    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    const patch = requests.find((r) => r.method === "PATCH");
    expect(patch?.body).toEqual({ category_id: suggested.id });
  });

  it("hides the suggestion line but keeps the recompute button when already current", async () => {
    mockApi();
    const suggested = category({ name: "Billing" });
    render(
      <CategorySuggestion
        ticket={ticketDetail({ category_id: suggested.id, ai_suggested_category: suggested })}
        onChanged={vi.fn()}
      />,
    );

    await screen.findByRole("button", { name: "Recompute suggestion" });
    expect(screen.queryByText(/Suggests:/)).not.toBeInTheDocument();
  });

  it("renders nothing when no categories are configured", async () => {
    mockApi({ categories: [] });
    const { container } = render(
      <CategorySuggestion ticket={ticketDetail()} onChanged={vi.fn()} />,
    );

    await waitFor(() => expect(container.firstChild).toBeNull());
  });

  it("clicking Suggest category calls the recompute endpoint", async () => {
    const requests = mockApi();
    const onChanged = vi.fn();
    const user = userEvent.setup();

    render(<CategorySuggestion ticket={ticketDetail()} onChanged={onChanged} />);

    await user.click(await screen.findByRole("button", { name: "Suggest category" }));

    await waitFor(() =>
      expect(requests.some((r) => r.method === "POST" && r.url.includes("/ai/suggested-category"))).toBe(
        true,
      ),
    );
    expect(onChanged).toHaveBeenCalled();
  });
});
