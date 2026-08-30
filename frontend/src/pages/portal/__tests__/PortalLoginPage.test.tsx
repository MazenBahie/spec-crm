import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import PortalLoginPage from "../PortalLoginPage";
import { clearPortalSession, getPortalToken } from "../../../api/portalAuth";

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/portal/login"]}>
      <Routes>
        <Route path="/portal/login" element={<PortalLoginPage />} />
        <Route path="/portal/tickets" element={<h1>Your tickets</h1>} />
      </Routes>
    </MemoryRouter>,
  );
}

function mockFetch(response: { status: number; body: unknown }) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(response.body), { status: response.status })),
  );
}

describe("PortalLoginPage", () => {
  beforeEach(() => {
    clearPortalSession();
  });

  it("stores the token and navigates to the ticket list on success", async () => {
    mockFetch({
      status: 200,
      body: {
        token: "a-real-token",
        expires_at: "2026-09-13T00:00:00Z",
        portal_user: {
          id: crypto.randomUUID(),
          customer_id: crypto.randomUUID(),
          email: "owner@example.com",
          display_name: "Owner",
        },
      },
    });
    const user = userEvent.setup();
    renderPage();

    await user.type(screen.getByLabelText("Email"), "owner@example.com");
    await user.type(screen.getByLabelText("Password"), "hunter2pass");
    await user.click(screen.getByRole("button", { name: "Log in" }));

    expect(await screen.findByRole("heading", { name: "Your tickets" })).toBeInTheDocument();
    expect(getPortalToken()).toBe("a-real-token");
  });

  it("renders a 403 failure in an alert without navigating", async () => {
    mockFetch({ status: 403, body: { detail: "no matching customer account for this email" } });
    const user = userEvent.setup();
    renderPage();

    await user.type(screen.getByLabelText("Email"), "owner@example.com");
    await user.type(screen.getByLabelText("Password"), "wrongpassword");
    await user.click(screen.getByRole("button", { name: "Log in" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "no matching customer account for this email",
    );
    expect(screen.queryByRole("heading", { name: "Your tickets" })).not.toBeInTheDocument();
    expect(getPortalToken()).toBeNull();
  });
});
