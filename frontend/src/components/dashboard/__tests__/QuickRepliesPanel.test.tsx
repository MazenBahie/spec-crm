import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import QuickRepliesPanel from "../QuickRepliesPanel";
import type { QuickReply } from "../../../types/agent";

const AGENT_ID = "11111111-1111-4111-8111-111111111111";

function reply(overrides: Partial<QuickReply> = {}): QuickReply {
  const scope = overrides.scope ?? "personal";
  return {
    id: crypto.randomUUID(),
    scope,
    // Mirrors the server rule: personal replies have an owner, team ones don't.
    owner_agent_id: scope === "personal" ? AGENT_ID : null,
    shortcut: null,
    title: "Greeting",
    body: "Hi {{customer.first_name}}!",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

interface Recorded {
  method: string;
  url: string;
  body: Record<string, unknown> | undefined;
}

function mockApi(initial: QuickReply[]) {
  const requests: Recorded[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = (init?.method ?? "GET").toUpperCase();
      const body = init?.body ? JSON.parse(String(init.body)) : undefined;
      requests.push({ method, url, body });

      const json = (payload: unknown, status = 200) =>
        new Response(status === 204 ? null : JSON.stringify(payload), {
          status,
          headers: { "Content-Type": "application/json" },
        });

      if (method === "POST" || method === "PATCH") {
        // Stand in for the server, which derives ownership from scope.
        const scope = (body?.scope as QuickReply["scope"]) ?? "personal";
        const id = method === "PATCH" ? url.split("/quick-replies/")[1] : crypto.randomUUID();
        return json(
          {
            ...reply({ scope }),
            ...body,
            id,
            owner_agent_id: scope === "personal" ? AGENT_ID : null,
          },
          method === "POST" ? 201 : 200,
        );
      }
      if (method === "DELETE") return json(null, 204);
      return json(initial);
    }),
  );
  return requests;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("QuickRepliesPanel", () => {
  it("lists replies with a scope badge", async () => {
    mockApi([
      reply({ title: "Shared apology", scope: "team" }),
      reply({ title: "My greeting", scope: "personal", shortcut: "hi" }),
    ]);
    render(<QuickRepliesPanel />);

    const shared = (await screen.findByText("Shared apology")).closest("li")!;
    expect(within(shared).getByText("team")).toBeInTheDocument();

    const mine = screen.getByText("My greeting").closest("li")!;
    expect(within(mine).getByText("personal")).toBeInTheDocument();
    expect(within(mine).getByText("/hi")).toBeInTheDocument();
  });

  it("shows the stored template, not a rendered version", async () => {
    mockApi([reply({ body: "Hi {{customer.first_name}}, re {{ticket.reference}}" })]);
    render(<QuickRepliesPanel />);

    expect(
      await screen.findByText("Hi {{customer.first_name}}, re {{ticket.reference}}"),
    ).toBeInTheDocument();
  });

  it("shows an empty state", async () => {
    mockApi([]);
    render(<QuickRepliesPanel />);

    expect(
      await screen.findByText("No quick replies yet — the one above will be the first."),
    ).toBeInTheDocument();
  });

  it("creates a personal reply, never sending an owner", async () => {
    const requests = mockApi([]);
    const user = userEvent.setup();

    render(<QuickRepliesPanel />);
    await screen.findByText("No quick replies yet — the one above will be the first.");

    await user.type(screen.getByLabelText("Quick reply title"), "Greeting");
    await user.type(screen.getByLabelText("Quick reply shortcut"), "hi");
    await user.type(screen.getByLabelText("Quick reply body"), "Hello there");
    await user.click(screen.getByRole("button", { name: "Add quick reply" }));

    await waitFor(() => expect(requests.some((r) => r.method === "POST")).toBe(true));
    const posted = requests.find((r) => r.method === "POST")!;
    expect(posted.body).toEqual({
      scope: "personal",
      title: "Greeting",
      body: "Hello there",
      shortcut: "hi",
    });
    // Ownership is the server's to decide — sending one is the only way to
    // break the scope invariant, so the client never does.
    expect(posted.body).not.toHaveProperty("owner_agent_id");
    expect(await screen.findByText("Hello there")).toBeInTheDocument();
  });

  it("creates a team reply when the scope is switched", async () => {
    const requests = mockApi([]);
    const user = userEvent.setup();

    render(<QuickRepliesPanel />);
    await screen.findByText("No quick replies yet — the one above will be the first.");

    await user.type(screen.getByLabelText("Quick reply title"), "Shared");
    await user.type(screen.getByLabelText("Quick reply body"), "Team text");
    await user.selectOptions(screen.getByLabelText("Quick reply scope"), "team");
    await user.click(screen.getByRole("button", { name: "Add quick reply" }));

    await waitFor(() => expect(requests.some((r) => r.method === "POST")).toBe(true));
    expect(requests.find((r) => r.method === "POST")!.body).toMatchObject({ scope: "team" });

    const created = (await screen.findByText("Shared")).closest("li")!;
    expect(within(created).getByText("team")).toBeInTheDocument();
  });

  it("promoting a personal reply to the team clears its owner", async () => {
    const existing = reply({ title: "Greeting", scope: "personal" });
    expect(existing.owner_agent_id).toBe(AGENT_ID);
    const requests = mockApi([existing]);
    const user = userEvent.setup();

    render(<QuickRepliesPanel />);
    await user.click(await screen.findByLabelText("Edit Greeting"));

    await user.selectOptions(screen.getByLabelText("Edit scope"), "team");
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(requests.some((r) => r.method === "PATCH")).toBe(true));
    expect(requests.find((r) => r.method === "PATCH")!.body).toMatchObject({ scope: "team" });

    const row = (await screen.findByText("Greeting")).closest("li")!;
    expect(within(row).getByText("team")).toBeInTheDocument();
    expect(within(row).queryByText("personal")).not.toBeInTheDocument();
  });

  it("edits a reply in place", async () => {
    const requests = mockApi([reply({ title: "Greeting", body: "Old text" })]);
    const user = userEvent.setup();

    render(<QuickRepliesPanel />);
    await user.click(await screen.findByLabelText("Edit Greeting"));

    const bodyBox = screen.getByLabelText("Edit body");
    await user.clear(bodyBox);
    await user.type(bodyBox, "New text");
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(requests.some((r) => r.method === "PATCH")).toBe(true));
    expect(await screen.findByText("New text")).toBeInTheDocument();
    expect(screen.queryByLabelText("Edit body")).not.toBeInTheDocument();
  });

  it("cancelling an edit changes nothing", async () => {
    const requests = mockApi([reply({ title: "Greeting", body: "Old text" })]);
    const user = userEvent.setup();

    render(<QuickRepliesPanel />);
    await user.click(await screen.findByLabelText("Edit Greeting"));
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.getByText("Old text")).toBeInTheDocument();
    expect(requests.some((r) => r.method === "PATCH")).toBe(false);
  });

  it("asks before deleting, and honours a refusal", async () => {
    const requests = mockApi([reply({ title: "Greeting" })]);
    const user = userEvent.setup();
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);

    render(<QuickRepliesPanel />);
    await user.click(await screen.findByLabelText("Delete Greeting"));

    expect(confirm).toHaveBeenCalled();
    expect(requests.some((r) => r.method === "DELETE")).toBe(false);
    expect(screen.getByText("Greeting")).toBeInTheDocument();
  });

  it("deletes on confirmation", async () => {
    const requests = mockApi([reply({ title: "Greeting" })]);
    const user = userEvent.setup();
    vi.spyOn(window, "confirm").mockReturnValue(true);

    render(<QuickRepliesPanel />);
    await user.click(await screen.findByLabelText("Delete Greeting"));

    await waitFor(() => expect(requests.some((r) => r.method === "DELETE")).toBe(true));
    await waitFor(() => expect(screen.queryByText("Greeting")).not.toBeInTheDocument());
  });

  it("surfaces a 403 when editing someone else's personal reply", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
        const method = (init?.method ?? "GET").toUpperCase();
        if (method === "GET") {
          return new Response(JSON.stringify([reply({ title: "Greeting" })]), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        return new Response(
          JSON.stringify({ detail: "that quick reply belongs to another agent" }),
          { status: 403, headers: { "Content-Type": "application/json" } },
        );
      }),
    );
    const user = userEvent.setup();

    render(<QuickRepliesPanel />);
    await user.click(await screen.findByLabelText("Edit Greeting"));
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("another agent");
  });
});
