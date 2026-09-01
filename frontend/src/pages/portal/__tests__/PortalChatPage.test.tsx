import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import PortalChatPage from "../PortalChatPage";
import type { ChatbotMessage } from "../../../types/chatbot";

const SESSION_ID = "77777777-7777-4777-8777-777777777777";

function message(overrides: Partial<ChatbotMessage> = {}): ChatbotMessage {
  return {
    id: crypto.randomUUID(),
    session_id: SESSION_ID,
    role: "user",
    content: "hello",
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function mockFetch(opts: {
  history?: ChatbotMessage[];
  turnResponseStatus?: number;
}) {
  const requests: { method: string; url: string }[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method ?? "GET").toUpperCase();
    requests.push({ method, url });
    const json = (payload: unknown, status = 200) =>
      new Response(JSON.stringify(payload), { status, headers: { "Content-Type": "application/json" } });

    if (url.includes("/sessions") && method === "POST" && !url.includes("/messages")) {
      return json({
        id: SESSION_ID,
        portal_user_id: crypto.randomUUID(),
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      });
    }
    if (url.includes("/messages") && method === "GET") {
      return json(opts.history ?? []);
    }
    if (url.includes("/messages") && method === "POST") {
      if (opts.turnResponseStatus && opts.turnResponseStatus >= 400) {
        return json({ detail: "assistant unavailable" }, opts.turnResponseStatus);
      }
      const body = JSON.parse(String(init?.body)) as { content: string };
      return json({
        user_message: message({ content: body.content }),
        assistant_message: message({ role: "assistant", content: "Here is help." }),
      });
    }
    return json({});
  });
  vi.stubGlobal("fetch", fetchMock);
  return requests;
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/portal/chat"]}>
      <Routes>
        <Route path="/portal/chat" element={<PortalChatPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("PortalChatPage", () => {
  it("shows the empty-history placeholder on first render", async () => {
    mockFetch({ history: [] });
    renderPage();

    expect(
      await screen.findByText("Ask a question and the assistant will look through our help center for you."),
    ).toBeInTheDocument();
  });

  it("sending a message updates the thread and labels the assistant reply", async () => {
    mockFetch({ history: [] });
    const user = userEvent.setup();
    renderPage();

    await screen.findByLabelText("Your message");
    await user.type(screen.getByLabelText("Your message"), "How do I reset my password?");
    await user.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByText("Here is help.")).toBeInTheDocument();
    expect(screen.getByText("How do I reset my password?")).toBeInTheDocument();
    expect(screen.getByText("AI Assistant")).toBeInTheDocument();
    expect(screen.getByLabelText("Your message")).toHaveValue("");
  });

  it("shows an error and keeps the draft recoverable when sending fails", async () => {
    mockFetch({ history: [], turnResponseStatus: 409 });
    const user = userEvent.setup();
    renderPage();

    await screen.findByLabelText("Your message");
    await user.type(screen.getByLabelText("Your message"), "my question");
    await user.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("assistant unavailable");
    // The optimistic bubble is rolled back and the typed text recoverable.
    await waitFor(() => expect(screen.getByLabelText("Your message")).toHaveValue("my question"));
  });
});
