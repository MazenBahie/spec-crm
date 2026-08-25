import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import App from "../App";

/** Answer health and customer-list calls so both routes can render. */
function mockBackend() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      const payload = url.includes("/health")
        ? { status: "ok" }
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

describe("app navigation", () => {
  it("renders the health page at / without regression", async () => {
    mockBackend();
    renderApp("/");

    expect(await screen.findByText("CRM — System Health")).toBeInTheDocument();
    expect(await screen.findByText("ok")).toBeInTheDocument();
  });

  it("exposes Customers in the main navigation", async () => {
    mockBackend();
    renderApp("/");

    // Let the health fetch settle first so no state update escapes the test.
    await screen.findByText("CRM — System Health");

    const link = screen.getByRole("link", { name: "Customers" });
    expect(link).toHaveAttribute("href", "/customers");
  });

  it("navigates from / to the customers list via the nav link", async () => {
    mockBackend();
    const user = userEvent.setup();
    renderApp("/");

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
    expect(screen.getByRole("link", { name: "Health" })).not.toHaveAttribute(
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
});
