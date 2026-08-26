import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import TasksPanel from "../TasksPanel";
import type { AgentTask } from "../../../types/agent";

const AGENT_ID = "11111111-1111-4111-8111-111111111111";

function task(overrides: Partial<AgentTask> = {}): AgentTask {
  return {
    id: crypto.randomUUID(),
    agent_id: AGENT_ID,
    title: "Call Ali",
    notes: null,
    status: "open",
    remind_at: null,
    ticket_id: null,
    customer_id: null,
    completed_at: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

/** An ISO timestamp at midday in the viewer's own zone, today. */
function todayAtNoon(): string {
  const when = new Date();
  when.setHours(12, 0, 0, 0);
  return when.toISOString();
}

function daysFromNow(days: number): string {
  return new Date(Date.now() + days * 86_400_000).toISOString();
}

interface Recorded {
  method: string;
  url: string;
  body: unknown;
}

/** Route GET /tasks to `initial`; POST/other methods answer from `handlers`. */
function mockApi(
  initial: AgentTask[],
  handlers: {
    created?: AgentTask;
    failComplete?: boolean;
    failCreate?: boolean;
    failDelete?: boolean;
  } = {},
) {
  const requests: Recorded[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = (init?.method ?? "GET").toUpperCase();
      requests.push({
        method,
        url,
        body: init?.body ? JSON.parse(String(init.body)) : undefined,
      });

      const json = (payload: unknown, status = 200) =>
        new Response(status === 204 ? null : JSON.stringify(payload), {
          status,
          headers: { "Content-Type": "application/json" },
        });
      const boom = (detail: string) => json({ detail }, 500);

      if (url.includes("/complete") || url.includes("/reopen")) {
        if (handlers.failComplete) return boom("could not save");
        const id = url.split("/tasks/")[1].split("/")[0];
        const found = initial.find((t) => t.id === id)!;
        const done = url.includes("/complete");
        return json({
          ...found,
          status: done ? "done" : "open",
          completed_at: done ? "2026-02-02T00:00:00Z" : null,
        });
      }
      if (method === "POST") {
        if (handlers.failCreate) return boom("could not save");
        return json(handlers.created ?? task({ title: "Call Ali" }), 201);
      }
      if (method === "DELETE") {
        if (handlers.failDelete) return boom("could not delete");
        return json(null, 204);
      }
      return json(initial);
    }),
  );
  return requests;
}

describe("TasksPanel", () => {
  it("lists the agent's open tasks", async () => {
    mockApi([task({ title: "Call Ali" }), task({ title: "Email Globex" })]);
    render(<TasksPanel />);

    expect(await screen.findByText("Call Ali")).toBeInTheDocument();
    expect(screen.getByText("Email Globex")).toBeInTheDocument();
  });

  it("shows an empty state rather than a spinner", async () => {
    mockApi([]);
    render(<TasksPanel />);

    expect(await screen.findByText("No tasks yet. Add the first one above.")).toBeInTheDocument();
  });

  it("creates a task and shows it without a refetch", async () => {
    const requests = mockApi([], { created: task({ title: "Chase refund" }) });
    const user = userEvent.setup();

    render(<TasksPanel />);
    await screen.findByText("No tasks yet. Add the first one above.");

    await user.type(screen.getByLabelText("New task"), "Chase refund");
    await user.click(screen.getByRole("button", { name: "Add" }));

    expect(await screen.findByText("Chase refund")).toBeInTheDocument();
    const posted = requests.find((r) => r.method === "POST")!;
    expect(posted.body).toEqual({ title: "Chase refund", remind_at: null });
  });

  it("will not submit an empty title", async () => {
    const requests = mockApi([]);
    const user = userEvent.setup();

    render(<TasksPanel />);
    await screen.findByText("No tasks yet. Add the first one above.");

    expect(screen.getByRole("button", { name: "Add" })).toBeDisabled();
    await user.type(screen.getByLabelText("New task"), "   ");
    expect(screen.getByRole("button", { name: "Add" })).toBeDisabled();
    expect(requests.some((r) => r.method === "POST")).toBe(false);
  });

  it("completes a task optimistically", async () => {
    const existing = task({ title: "Call Ali" });
    const requests = mockApi([existing]);
    const user = userEvent.setup();

    render(<TasksPanel />);
    const checkbox = await screen.findByLabelText("Complete Call Ali");

    await user.click(checkbox);

    // Checked straight away, before the request has been answered.
    expect(checkbox).toBeChecked();
    await waitFor(() =>
      expect(requests.some((r) => r.url.includes("/complete"))).toBe(true),
    );
  });

  it("rolls back and reports when completing fails", async () => {
    const existing = task({ title: "Call Ali" });
    mockApi([existing], { failComplete: true });
    const user = userEvent.setup();

    render(<TasksPanel />);
    const checkbox = await screen.findByLabelText("Complete Call Ali");

    await user.click(checkbox);

    expect(await screen.findByRole("alert")).toHaveTextContent("could not save");
    // Back to unchecked — the optimistic flip was undone.
    await waitFor(() => expect(screen.getByLabelText("Complete Call Ali")).not.toBeChecked());
  });

  it("filters to tasks due today", async () => {
    mockApi([
      task({ title: "Due today", remind_at: todayAtNoon() }),
      task({ title: "Due next week", remind_at: daysFromNow(7) }),
      task({ title: "No reminder" }),
    ]);
    const user = userEvent.setup();

    render(<TasksPanel />);
    await screen.findByText("Due today");

    await user.click(screen.getByRole("button", { name: "Due today" }));

    const list = screen.getByRole("list");
    expect(within(list).getByText("Due today")).toBeInTheDocument();
    expect(within(list).queryByText("Due next week")).not.toBeInTheDocument();
    expect(within(list).queryByText("No reminder")).not.toBeInTheDocument();
  });

  it("hides completed tasks under the open filter and shows them under all", async () => {
    mockApi([
      task({ title: "Still open" }),
      task({ title: "Already done", status: "done", completed_at: "2026-01-02T00:00:00Z" }),
    ]);
    const user = userEvent.setup();

    render(<TasksPanel />);
    await screen.findByText("Still open");
    expect(screen.queryByText("Already done")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "All" }));
    expect(screen.getByText("Already done")).toBeInTheDocument();
  });

  it("shows a distinct empty state when nothing is due today", async () => {
    mockApi([task({ title: "Due next week", remind_at: daysFromNow(7) })]);
    const user = userEvent.setup();

    render(<TasksPanel />);
    await screen.findByText("Due next week");

    await user.click(screen.getByRole("button", { name: "Due today" }));
    expect(screen.getByText("Nothing due today.")).toBeInTheDocument();
  });

  it("deletes a task, restoring it if the request fails", async () => {
    mockApi([task({ title: "Call Ali" })], { failDelete: true });
    const user = userEvent.setup();

    render(<TasksPanel />);
    await screen.findByText("Call Ali");

    await user.click(screen.getByLabelText("Delete Call Ali"));

    expect(await screen.findByRole("alert")).toHaveTextContent("could not delete");
    expect(screen.getByText("Call Ali")).toBeInTheDocument();
  });

  it("surfaces an API error from the initial load", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(JSON.stringify({ detail: "a valid X-Agent-Id header is required" }), {
            status: 401,
            headers: { "Content-Type": "application/json" },
          }),
      ),
    );

    render(<TasksPanel />);

    expect(await screen.findByRole("alert")).toHaveTextContent("X-Agent-Id");
  });
});
