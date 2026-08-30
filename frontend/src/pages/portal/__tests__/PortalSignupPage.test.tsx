import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import PortalSignupPage from "../PortalSignupPage";

function renderPage() {
  return render(
    <MemoryRouter>
      <PortalSignupPage />
    </MemoryRouter>,
  );
}

function mockFetch(status: number, detail: string) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify({ detail }), { status })),
  );
}

async function fillAndSubmit(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText("Your name"), "New Owner");
  await user.type(screen.getByLabelText("Email"), "owner@example.com");
  await user.type(screen.getByLabelText("Password (minimum 8 characters)"), "hunter2pass");
  await user.click(screen.getByRole("button", { name: "Sign up" }));
}

describe("PortalSignupPage", () => {
  it("shows the 403 'no matching account' message", async () => {
    mockFetch(403, "no matching customer account for this email");
    const user = userEvent.setup();
    renderPage();

    await fillAndSubmit(user);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "no matching customer account for this email",
    );
  });

  it("shows the 409 'already registered' message", async () => {
    mockFetch(409, "an account with this email already exists");
    const user = userEvent.setup();
    renderPage();

    await fillAndSubmit(user);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "an account with this email already exists",
    );
  });
});
