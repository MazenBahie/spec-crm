import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import TicketWorkflowPanel from "../TicketWorkflowPanel";
import type { Agent, Ticket } from "../../../types/ticket";

function ticket(overrides: Partial<Ticket> = {}): Ticket {
  return {
    id: "22222222-2222-4222-8222-222222222222",
    reference: "TCK-22222222",
    customer_id: crypto.randomUUID(),
    category_id: null,
    ai_suggested_category_id: null,
    assignee_id: null,
    subject: "x",
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
    ...overrides,
  };
}

function agent(overrides: Partial<Agent> = {}): Agent {
  return {
    id: crypto.randomUUID(),
    display_name: "Dana",
    email: null,
    is_active: true,
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

interface Recorded {
  method: string;
  url: string;
  body: unknown;
}

function mockApi(agents: Agent[], responder?: (url: string, method: string) => Response | null) {
  const requests: Recorded[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method ?? "GET").toUpperCase();
    requests.push({ method, url, body: init?.body ? JSON.parse(String(init.body)) : undefined });

    if (url.includes("/agents") && method === "GET") {
      return new Response(JSON.stringify(agents), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    const custom = responder?.(url, method);
    if (custom) return custom;

    return new Response(JSON.stringify(ticket()), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  return requests;
}

describe("TicketWorkflowPanel", () => {
  it("offers only the transitions legal from the current status", async () => {
    mockApi([]);
    render(<TicketWorkflowPanel ticket={ticket({ status: "open" })} onChanged={vi.fn()} />);

    const select = await screen.findByLabelText("Move to status");
    const options = within(select)
      .getAllByRole("option")
      .map((o) => (o as HTMLOptionElement).value)
      .filter(Boolean);
    expect(options).toEqual(["triaged", "in_progress", "closed"]);
  });

  it("posts the chosen status with the comment", async () => {
    const requests = mockApi([]);
    const onChanged = vi.fn();
    const user = userEvent.setup();

    render(<TicketWorkflowPanel ticket={ticket({ status: "open" })} onChanged={onChanged} />);

    await user.type(screen.getByLabelText(/Comment/), "moving forward");
    await user.selectOptions(await screen.findByLabelText("Move to status"), "triaged");

    await waitFor(() =>
      expect(requests.some((r) => r.url.includes("/status") && r.method === "POST")).toBe(true),
    );
    const statusRequest = requests.find((r) => r.url.includes("/status"))!;
    expect(statusRequest.body).toEqual({ status: "triaged", comment: "moving forward" });
    expect(onChanged).toHaveBeenCalled();
  });

  it("disables Escalate when the ticket is terminal", async () => {
    mockApi([]);
    render(<TicketWorkflowPanel ticket={ticket({ status: "closed" })} onChanged={vi.fn()} />);
    expect(await screen.findByRole("button", { name: /Escalate/ })).toBeDisabled();
  });

  it("disables Escalate at the maximum escalation level", async () => {
    mockApi([]);
    render(
      <TicketWorkflowPanel ticket={ticket({ escalation_level: 3 })} onChanged={vi.fn()} />,
    );
    expect(await screen.findByRole("button", { name: /Escalate/ })).toBeDisabled();
  });

  it("enables Escalate below the maximum on a non-terminal ticket", async () => {
    mockApi([]);
    render(
      <TicketWorkflowPanel ticket={ticket({ escalation_level: 1, status: "open" })} onChanged={vi.fn()} />,
    );
    expect(await screen.findByRole("button", { name: /Escalate/ })).toBeEnabled();
  });

  it("renders a server 409 in the error banner", async () => {
    const requests = mockApi([], (url, method) => {
      if (url.includes("/status") && method === "POST") {
        return new Response(JSON.stringify({ detail: "cannot move ticket from open to resolved" }), {
          status: 409,
          headers: { "Content-Type": "application/json" },
        });
      }
      return null;
    });
    const user = userEvent.setup();

    render(<TicketWorkflowPanel ticket={ticket({ status: "open" })} onChanged={vi.fn()} />);
    await user.selectOptions(await screen.findByLabelText("Move to status"), "in_progress");

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "cannot move ticket from open to resolved",
    );
    expect(requests.some((r) => r.url.includes("/status"))).toBe(true);
  });

  it("assigning posts to /assignment", async () => {
    const dana = agent({ display_name: "Dana" });
    const requests = mockApi([dana]);
    const user = userEvent.setup();

    render(<TicketWorkflowPanel ticket={ticket()} onChanged={vi.fn()} />);
    await user.selectOptions(await screen.findByLabelText("Assignee"), dana.id);

    await waitFor(() =>
      expect(requests.some((r) => r.url.includes("/assignment") && r.method === "POST")).toBe(true),
    );
    const assignRequest = requests.find((r) => r.url.includes("/assignment"))!;
    expect(assignRequest.body).toEqual({ assignee_id: dana.id });
  });
});
