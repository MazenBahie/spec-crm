import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import App from "../App";
import { clearAgentId, setAgentId } from "../api/agentContext";
import { clearPortalSession } from "../api/portalAuth";

const AGENT_ID = "11111111-1111-4111-8111-111111111111";

const AGENTS = [
  { id: AGENT_ID, display_name: "Dana Support", email: "dana@crm.test", is_active: true },
];

/** Answer health, list, and lookup calls so every route can render. */
function mockBackend() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      // Bare objects, bare arrays, and pages — matched most specific first.
      const payload = url.includes("/health")
        ? { status: "ok" }
        : url.includes("/dashboard/summary")
          ? { open_assigned: 0, overdue: 0, tasks_due_today: 0, unread_mentions: 0 }
          : url.includes("/agents")
            ? AGENTS
            : url.includes("/ticket-categories") ||
                url.includes("/quick-replies") ||
                url.includes("/tasks") ||
                url.includes("/dashboard/")
              ? []
              : { items: [], total: 0 };
      return new Response(JSON.stringify(payload), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }),
  );
}

function renderApp(initialPath = "/") {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <App />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  // The agent id lives in module state, so it survives between tests unless
  // each one says what it wants. Cleared before mounting, never during: it is
  // an external store, and changing it under a subscribed component would be a
  // state update outside `act`.
  cleanup();
  clearAgentId();
  clearPortalSession();
});

describe("app navigation", () => {
  it("redirects / to the dashboard", async () => {
    mockBackend();
    setAgentId(AGENT_ID);
    renderApp("/");

    expect(
      await screen.findByRole("heading", { level: 1, name: "Dashboard" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Dashboard" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("asks which agent is on shift when none has been picked", async () => {
    mockBackend();
    renderApp("/dashboard");

    expect(
      await screen.findByRole("heading", { level: 1, name: "Who is on shift?" }),
    ).toBeInTheDocument();
    // Picking one swaps the placeholder for the real dashboard.
    await userEvent.setup().click(await screen.findByRole("button", { name: "Dana Support" }));
    expect(
      await screen.findByRole("heading", { level: 1, name: "Dashboard" }),
    ).toBeInTheDocument();
  });

  it("exposes Dashboard in the main navigation", async () => {
    mockBackend();
    setAgentId(AGENT_ID);
    renderApp("/dashboard");

    await screen.findByRole("heading", { level: 1, name: "Dashboard" });
    expect(screen.getByRole("link", { name: "Dashboard" })).toHaveAttribute(
      "href",
      "/dashboard",
    );
  });

  it("still renders the health page, now at /health", async () => {
    mockBackend();
    renderApp("/health");

    expect(await screen.findByText("CRM — System Health")).toBeInTheDocument();
    expect(await screen.findByText("ok")).toBeInTheDocument();
  });

  it("exposes Customers in the main navigation", async () => {
    mockBackend();
    renderApp("/health");
    await screen.findByText("CRM — System Health");

    const link = screen.getByRole("link", { name: "Customers" });
    expect(link).toHaveAttribute("href", "/customers");
  });

  it("navigates from /health to the customers list via the nav link", async () => {
    mockBackend();
    const user = userEvent.setup();
    renderApp("/health");

    await screen.findByText("CRM — System Health");
    await user.click(screen.getByRole("link", { name: "Customers" }));

    expect(
      await screen.findByRole("heading", { level: 1, name: "Customers" }),
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByRole("link", { name: "New customer" })).toBeInTheDocument(),
    );
  });

  it("marks the active nav item", async () => {
    mockBackend();
    renderApp("/customers");

    await screen.findByRole("heading", { level: 1, name: "Customers" });
    expect(screen.getByRole("link", { name: "Customers" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.getByRole("link", { name: "Dashboard" })).not.toHaveAttribute(
      "aria-current",
    );
  });

  it("renders the create form at /customers/new", async () => {
    mockBackend();
    renderApp("/customers/new");

    expect(
      await screen.findByRole("heading", { level: 1, name: "New customer" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Name (required)")).toBeInTheDocument();
  });

  it("shows a not-found page for unknown routes", () => {
    mockBackend();
    renderApp("/nope");
    expect(screen.getByRole("heading", { name: "Not found" })).toBeInTheDocument();
  });

  it("exposes Tickets in the main navigation", async () => {
    mockBackend();
    renderApp("/health");
    await screen.findByText("CRM — System Health");

    const link = screen.getByRole("link", { name: "Tickets" });
    expect(link).toHaveAttribute("href", "/tickets");
  });

  it("navigates from /health to the tickets queue via the nav link", async () => {
    mockBackend();
    const user = userEvent.setup();
    renderApp("/health");

    await screen.findByText("CRM — System Health");
    await user.click(screen.getByRole("link", { name: "Tickets" }));

    expect(
      await screen.findByRole("heading", { level: 1, name: "Tickets" }),
    ).toBeInTheDocument();
  });

  it("renders the ticket create form at /tickets/new", async () => {
    mockBackend();
    renderApp("/tickets/new");

    expect(
      await screen.findByRole("heading", { level: 1, name: "New ticket" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Subject (required)")).toBeInTheDocument();
  });

  it("marks Tickets as the active nav item at /tickets", async () => {
    mockBackend();
    renderApp("/tickets");

    await screen.findByRole("heading", { level: 1, name: "Tickets" });
    expect(screen.getByRole("link", { name: "Tickets" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.getByRole("link", { name: "Customers" })).not.toHaveAttribute(
      "aria-current",
    );
  });
});

describe("customer portal", () => {
  it("redirects /portal/tickets to /portal/login when no session is stored", async () => {
    mockBackend();
    renderApp("/portal/tickets");

    expect(
      await screen.findByRole("heading", { level: 1, name: "Log in" }),
    ).toBeInTheDocument();
  });

  it("never renders the agent nav bar under /portal", async () => {
    mockBackend();
    renderApp("/portal/login");

    await screen.findByRole("heading", { level: 1, name: "Log in" });
    expect(screen.queryByRole("link", { name: "Dashboard" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Tickets" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Customers" })).not.toBeInTheDocument();
  });

  it("still renders the agent nav bar outside /portal", async () => {
    mockBackend();
    renderApp("/health");

    await screen.findByText("CRM — System Health");
    expect(screen.getByRole("link", { name: "Dashboard" })).toBeInTheDocument();
  });
});
