import { useRef, useState } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import QuickReplyPicker, { renderTemplate } from "../QuickReplyPicker";
import type { QuickReply } from "../../../types/agent";

const TICKET = {
  id: "44444444-4444-4444-8444-444444444444",
  reference: "TCK-44444444",
  subject: "Cannot log in",
};
const CUSTOMER = { display_name: "Ali Hassan" };
const AGENT = { display_name: "Dana Support" };

function reply(overrides: Partial<QuickReply> = {}): QuickReply {
  return {
    id: crypto.randomUUID(),
    scope: "personal",
    owner_agent_id: "11111111-1111-4111-8111-111111111111",
    shortcut: null,
    title: "Greeting",
    body: "Hi {{customer.first_name}}!",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function mockApi(replies: QuickReply[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        new Response(JSON.stringify(replies), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
    ),
  );
}

/** A minimal composer, so insertion can be observed the way it really works. */
function Composer({ initial = "" }: { initial?: string }) {
  const ref = useRef<HTMLTextAreaElement>(null);
  const [value, setValue] = useState(initial);
  return (
    <div>
      <QuickReplyPicker
        textareaRef={ref}
        value={value}
        onChange={setValue}
        context={{ ticket: TICKET, customer: CUSTOMER, agent: AGENT }}
      />
      <textarea ref={ref} aria-label="Message body" value={value} onChange={(e) => setValue(e.target.value)} />
    </div>
  );
}

describe("renderTemplate", () => {
  const context = { ticket: TICKET, customer: CUSTOMER, agent: AGENT };

  it("expands the documented tokens", () => {
    expect(renderTemplate("Hi {{customer.first_name}}!", context)).toBe("Hi Ali!");
    expect(renderTemplate("Re {{ticket.id}}", context)).toBe(`Re ${TICKET.id}`);
    expect(renderTemplate("Re {{ticket.reference}}", context)).toBe(`Re ${TICKET.reference}`);
    expect(renderTemplate("— {{agent.display_name}}", context)).toBe("— Dana Support");
  });

  it("tolerates whitespace inside the braces", () => {
    expect(renderTemplate("Hi {{ customer.first_name }}!", context)).toBe("Hi Ali!");
  });

  it("leaves an unknown token as literal text", () => {
    // A visible token is a mistake the agent can catch before sending; a
    // silent blank is not.
    expect(renderTemplate("Hi {{customer.nickname}}!", context)).toBe(
      "Hi {{customer.nickname}}!",
    );
  });

  it("leaves a known token literal when there is nothing behind it", () => {
    expect(renderTemplate("Hi {{customer.first_name}}!", {})).toBe(
      "Hi {{customer.first_name}}!",
    );
  });

  it("expands several tokens in one body", () => {
    expect(
      renderTemplate("Hi {{customer.first_name}}, re {{ticket.reference}} — {{agent.display_name}}", context),
    ).toBe("Hi Ali, re TCK-44444444 — Dana Support");
  });
});

describe("QuickReplyPicker", () => {
  it("inserts a rendered reply into the composer", async () => {
    mockApi([reply({ body: "Hi {{customer.first_name}}, about {{ticket.reference}}." })]);
    const user = userEvent.setup();

    render(<Composer />);
    await user.click(screen.getByRole("button", { name: /Quick reply/ }));
    await user.click(await screen.findByRole("option", { name: /Greeting/ }));

    expect(screen.getByLabelText("Message body")).toHaveValue(
      "Hi Ali, about TCK-44444444.",
    );
  });

  it("opens on Ctrl+/ from inside the composer", async () => {
    mockApi([reply()]);
    const user = userEvent.setup();

    render(<Composer />);
    const textarea = screen.getByLabelText("Message body");
    await user.click(textarea);
    await user.keyboard("{Control>}/{/Control}");

    expect(await screen.findByRole("listbox")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Quick reply/ })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
  });

  it("ignores Ctrl+/ pressed outside the composer", async () => {
    mockApi([reply()]);
    const user = userEvent.setup();

    render(
      <>
        <input aria-label="Somewhere else" />
        <Composer />
      </>,
    );
    await user.click(screen.getByLabelText("Somewhere else"));
    await user.keyboard("{Control>}/{/Control}");

    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  it("inserts at the caret rather than appending", async () => {
    mockApi([reply({ body: "[SNIPPET]" })]);
    const user = userEvent.setup();

    render(<Composer initial="Hello  — thanks" />);
    const textarea = screen.getByLabelText("Message body") as HTMLTextAreaElement;
    // Park the caret between the two spaces after "Hello".
    textarea.focus();
    textarea.setSelectionRange(6, 6);

    await user.click(screen.getByRole("button", { name: /Quick reply/ }));
    await user.click(await screen.findByRole("option", { name: /Greeting/ }));

    expect(textarea).toHaveValue("Hello [SNIPPET] — thanks");
  });

  it("replaces the selection when there is one", async () => {
    mockApi([reply({ body: "[NEW]" })]);
    const user = userEvent.setup();

    render(<Composer initial="keep REPLACE keep" />);
    const textarea = screen.getByLabelText("Message body") as HTMLTextAreaElement;
    textarea.focus();
    textarea.setSelectionRange(5, 12);

    await user.click(screen.getByRole("button", { name: /Quick reply/ }));
    await user.click(await screen.findByRole("option", { name: /Greeting/ }));

    expect(textarea).toHaveValue("keep [NEW] keep");
  });

  it("filters by title and shortcut", async () => {
    mockApi([
      reply({ title: "Greeting", shortcut: "hi" }),
      reply({ title: "Apology", shortcut: "sorry" }),
    ]);
    const user = userEvent.setup();

    render(<Composer />);
    await user.click(screen.getByRole("button", { name: /Quick reply/ }));

    const search = await screen.findByLabelText("Search quick replies");
    await user.type(search, "sorry");

    expect(screen.getByRole("option", { name: /Apology/ })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: /Greeting/ })).not.toBeInTheDocument();

    await user.clear(search);
    await user.type(search, "zzz");
    expect(screen.getByText("Nothing matches that.")).toBeInTheDocument();
  });

  it("closes on Escape", async () => {
    mockApi([reply()]);
    const user = userEvent.setup();

    render(<Composer />);
    await user.click(screen.getByRole("button", { name: /Quick reply/ }));
    await screen.findByRole("listbox");

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  it("points at the dashboard when the library is empty", async () => {
    mockApi([]);
    const user = userEvent.setup();

    render(<Composer />);
    await user.click(screen.getByRole("button", { name: /Quick reply/ }));

    expect(
      await screen.findByText("No quick replies yet. Add some from the dashboard."),
    ).toBeInTheDocument();
  });

  it("stays usable when the library cannot be loaded", async () => {
    // A quick-reply outage must not stop an agent replying to a customer.
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(JSON.stringify({ detail: "nope" }), {
            status: 401,
            headers: { "Content-Type": "application/json" },
          }),
      ),
    );
    const user = userEvent.setup();

    render(<Composer initial="typed by hand" />);
    await user.click(screen.getByRole("button", { name: /Quick reply/ }));

    await waitFor(() =>
      expect(
        screen.getByText("No quick replies yet. Add some from the dashboard."),
      ).toBeInTheDocument(),
    );
    expect(screen.getByLabelText("Message body")).toHaveValue("typed by hand");
  });
});
