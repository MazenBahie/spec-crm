import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import ContactDetailsPanel from "../ContactDetailsPanel";
import type { ContactDetail, ContactKind } from "../../../types/customer";

const CUSTOMER_ID = "11111111-1111-4111-8111-111111111111";

function contact(overrides: Partial<ContactDetail> = {}): ContactDetail {
  return {
    id: crypto.randomUUID(),
    customer_id: CUSTOMER_ID,
    kind: "phone",
    value: "+1 555 0100",
    label: null,
    is_primary: false,
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

interface Recorded {
  method: string;
  url: string;
  body: unknown;
}

/** Serve a contacts list; record every mutating call for assertions. */
function mockApi(initial: ContactDetail[]) {
  const requests: Recorded[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method ?? "GET").toUpperCase();
    requests.push({
      method,
      url,
      body: init?.body ? JSON.parse(String(init.body)) : undefined,
    });

    if (method === "GET") {
      return new Response(JSON.stringify(initial), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    if (method === "DELETE") return new Response(null, { status: 204 });
    return new Response(JSON.stringify(contact()), {
      status: 201,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  return requests;
}

function mutations(requests: Recorded[]): Recorded[] {
  return requests.filter((r) => r.method !== "GET");
}

describe("ContactDetailsPanel", () => {
  it("lists existing contacts", async () => {
    mockApi([
      contact({ kind: "phone", value: "+1 555 0100", label: "work" }),
      contact({ kind: "email", value: "ops@acme.test", is_primary: true }),
    ]);

    render(<ContactDetailsPanel customerId={CUSTOMER_ID} />);

    expect(await screen.findByText("+1 555 0100")).toBeInTheDocument();
    expect(screen.getByText("ops@acme.test")).toBeInTheDocument();
    expect(screen.getByText("work")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Demote ops@acme.test/ })).toHaveTextContent(
      "Primary ✓",
    );
  });

  it("shows an empty state", async () => {
    mockApi([]);
    render(<ContactDetailsPanel customerId={CUSTOMER_ID} />);
    expect(await screen.findByText("No contact details yet.")).toBeInTheDocument();
  });

  it("adds a contact and posts the trimmed payload", async () => {
    const requests = mockApi([]);
    const user = userEvent.setup();

    render(<ContactDetailsPanel customerId={CUSTOMER_ID} />);
    await screen.findByText("No contact details yet.");

    await user.selectOptions(screen.getByLabelText("Contact kind"), "email");
    await user.type(screen.getByLabelText("Contact value"), "  new@acme.test  ");
    await user.type(screen.getByLabelText("Contact label"), " work ");
    await user.click(screen.getByRole("button", { name: "Add" }));

    await waitFor(() => expect(mutations(requests).length).toBe(1));
    const posted = mutations(requests)[0];
    expect(posted.method).toBe("POST");
    expect(posted.url).toBe(`/api/customers/${CUSTOMER_ID}/contacts`);
    expect(posted.body).toEqual({
      kind: "email",
      value: "new@acme.test",
      label: "work",
      is_primary: false,
    });
  });

  it("disables the primary checkbox when that kind already has a primary", async () => {
    mockApi([contact({ kind: "phone", is_primary: true })]);
    render(<ContactDetailsPanel customerId={CUSTOMER_ID} />);

    await screen.findByText("+1 555 0100");

    // Default kind in the add form is "phone", which is already taken.
    expect(screen.getByRole("checkbox")).toBeDisabled();
    expect(
      screen.getByText(/A primary phone contact already exists/),
    ).toBeInTheDocument();
  });

  it("allows a primary of a kind that does not have one yet", async () => {
    const user = userEvent.setup();
    mockApi([contact({ kind: "phone", is_primary: true })]);
    render(<ContactDetailsPanel customerId={CUSTOMER_ID} />);
    await screen.findByText("+1 555 0100");

    await user.selectOptions(screen.getByLabelText("Contact kind"), "email");

    expect(screen.getByRole("checkbox")).toBeEnabled();
    expect(
      screen.queryByText(/A primary email contact already exists/),
    ).not.toBeInTheDocument();
  });

  it("blocks promoting a second primary of the same kind before submitting", async () => {
    const existingPrimary = contact({ kind: "email", value: "a@acme.test", is_primary: true });
    const other = contact({ kind: "email", value: "b@acme.test" });
    const requests = mockApi([existingPrimary, other]);
    const user = userEvent.setup();

    render(<ContactDetailsPanel customerId={CUSTOMER_ID} />);
    await screen.findByText("b@acme.test");

    await user.click(screen.getByRole("button", { name: "Promote b@acme.test" }));

    // The guard fires client-side: an error is shown and no PATCH is sent.
    expect(await screen.findByRole("alert")).toHaveTextContent(
      /A primary email contact already exists/,
    );
    expect(mutations(requests)).toEqual([]);
  });

  it("allows demoting the current primary", async () => {
    const primary = contact({ kind: "email", value: "a@acme.test", is_primary: true });
    const requests = mockApi([primary]);
    const user = userEvent.setup();

    render(<ContactDetailsPanel customerId={CUSTOMER_ID} />);
    await screen.findByText("a@acme.test");

    await user.click(screen.getByRole("button", { name: "Demote a@acme.test" }));

    await waitFor(() => expect(mutations(requests).length).toBe(1));
    expect(mutations(requests)[0].method).toBe("PATCH");
    expect(mutations(requests)[0].body).toEqual({ is_primary: false });
  });

  it("deletes a contact", async () => {
    const target = contact({ value: "+1 555 0199" });
    const requests = mockApi([target]);
    const user = userEvent.setup();

    render(<ContactDetailsPanel customerId={CUSTOMER_ID} />);
    await screen.findByText("+1 555 0199");

    await user.click(screen.getByRole("button", { name: "Delete +1 555 0199" }));

    await waitFor(() => expect(mutations(requests).length).toBe(1));
    expect(mutations(requests)[0].method).toBe("DELETE");
    expect(mutations(requests)[0].url).toBe(
      `/api/customers/${CUSTOMER_ID}/contacts/${target.id}`,
    );
  });

  it("surfaces a server 409 if it slips past the client guard", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
        if ((init?.method ?? "GET").toUpperCase() === "GET") {
          return new Response(JSON.stringify([]), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        return new Response(
          JSON.stringify({ detail: "a primary phone contact already exists" }),
          { status: 409, headers: { "Content-Type": "application/json" } },
        );
      }),
    );
    const user = userEvent.setup();

    render(<ContactDetailsPanel customerId={CUSTOMER_ID} />);
    await screen.findByText("No contact details yet.");

    await user.type(screen.getByLabelText("Contact value"), "+1 555 0100");
    await user.click(screen.getByRole("button", { name: "Add" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "a primary phone contact already exists",
    );
  });

  it("offers every contact kind", async () => {
    mockApi([]);
    render(<ContactDetailsPanel customerId={CUSTOMER_ID} />);
    await screen.findByText("No contact details yet.");

    const options = screen
      .getAllByRole("option")
      .map((option) => (option as HTMLOptionElement).value as ContactKind);
    expect(options).toEqual(["phone", "email", "address", "other"]);
  });
});
