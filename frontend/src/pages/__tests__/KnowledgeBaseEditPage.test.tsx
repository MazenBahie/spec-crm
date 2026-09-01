import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import KnowledgeBaseEditPage from "../KnowledgeBaseEditPage";
import type { Article } from "../../types/knowledgeBase";

const ARTICLE_ID = "22222222-2222-4222-8222-222222222222";

function article(overrides: Partial<Article> = {}): Article {
  return {
    id: ARTICLE_ID,
    slug: "reset-password",
    title: "Reset your password",
    summary: null,
    body: "Go to settings and click reset.",
    kind: "faq",
    status: "draft",
    category_id: null,
    view_count: 0,
    author_agent_id: null,
    published_at: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    category: null,
    ...overrides,
  };
}

interface Recorded {
  method: string;
  url: string;
  body: Record<string, unknown> | undefined;
}

function mockApi(existing: Article | null) {
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

      if (url.includes("/kb/categories")) return json({ items: [], total: 0 });
      if (url.endsWith("/publish")) {
        return json({ ...(existing ?? article()), status: "published", published_at: "2026-01-02T00:00:00Z" });
      }
      if (url.endsWith("/unpublish")) {
        return json({ ...(existing ?? article()), status: "draft" });
      }
      if (method === "GET" && url.includes(`/kb/articles/${ARTICLE_ID}`)) {
        if (!existing) return json({ detail: "not found" }, 404);
        return json(existing);
      }
      if (method === "POST") return json({ ...article(), ...body, id: crypto.randomUUID() }, 201);
      // A create redirects to /kb/:newId, which immediately re-fetches that
      // article -- answer any other article GET the same way a real create
      // would, with the just-created fields layered on the fixture.
      if (method === "GET" && url.includes("/kb/articles/")) {
        return json({ ...article(), ...(existing ?? {}) });
      }
      if (method === "PATCH") return json({ ...(existing ?? article()), ...body });
      if (method === "DELETE") return json(null, 204);
      return json({ items: [], total: 0 });
    }),
  );
  return requests;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

function renderNew() {
  return render(
    <MemoryRouter initialEntries={["/kb/new"]}>
      <Routes>
        <Route path="/kb/new" element={<KnowledgeBaseEditPage />} />
        <Route path="/kb/:id" element={<KnowledgeBaseEditPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

function renderEdit() {
  return render(
    <MemoryRouter initialEntries={[`/kb/${ARTICLE_ID}`]}>
      <Routes>
        <Route path="/kb/:id" element={<KnowledgeBaseEditPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("KnowledgeBaseEditPage", () => {
  it("disables submit until title and slug are filled", async () => {
    mockApi(null);
    renderNew();

    await screen.findByRole("heading", { level: 1, name: "New article" });
    expect(screen.getByRole("button", { name: "Create article" })).toBeDisabled();
  });

  it("auto-suggests a slug from the title, editably", async () => {
    mockApi(null);
    const user = userEvent.setup();
    renderNew();

    await screen.findByRole("heading", { level: 1, name: "New article" });
    await user.type(screen.getByLabelText("Title (required)"), "How to Reset Password!");

    expect(screen.getByLabelText("Slug (required)")).toHaveValue("how-to-reset-password");

    await user.clear(screen.getByLabelText("Slug (required)"));
    await user.type(screen.getByLabelText("Slug (required)"), "custom-slug");
    await user.type(screen.getByLabelText("Title (required)"), "!!!");

    expect(screen.getByLabelText("Slug (required)")).toHaveValue("custom-slug");
  });

  it("creates an article", async () => {
    const requests = mockApi(null);
    const user = userEvent.setup();
    renderNew();

    await screen.findByRole("heading", { level: 1, name: "New article" });
    await user.type(screen.getByLabelText("Title (required)"), "Reset your password");
    await user.type(screen.getByLabelText("Body (markdown)"), "Body text");
    await user.click(screen.getByRole("button", { name: "Create article" }));

    await waitFor(() => expect(requests.some((r) => r.method === "POST")).toBe(true));
    const posted = requests.find((r) => r.method === "POST")!;
    expect(posted.body).toMatchObject({ title: "Reset your password", slug: "reset-your-password" });
  });

  it("loads an existing article for editing", async () => {
    mockApi(article());
    renderEdit();

    expect(await screen.findByRole("heading", { level: 1, name: "Edit article" })).toBeInTheDocument();
    expect(screen.getByLabelText("Title (required)")).toHaveValue("Reset your password");
    expect(screen.getByText("Status: draft")).toBeInTheDocument();
  });

  it("publishes a draft article", async () => {
    const requests = mockApi(article());
    const user = userEvent.setup();
    renderEdit();

    await screen.findByRole("heading", { level: 1, name: "Edit article" });
    await user.click(screen.getByRole("button", { name: "Publish" }));

    await waitFor(() => expect(requests.some((r) => r.url.endsWith("/publish"))).toBe(true));
    expect(await screen.findByText("Status: published")).toBeInTheDocument();
  });

  it("surfaces a 409 when publishing an empty-body article fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = (init?.method ?? "GET").toUpperCase();
        if (url.includes("/kb/categories")) {
          return new Response(JSON.stringify({ items: [], total: 0 }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (method === "GET") {
          return new Response(JSON.stringify(article({ body: "" })), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.endsWith("/publish")) {
          return new Response(
            JSON.stringify({ detail: "cannot publish an article with an empty body" }),
            { status: 409, headers: { "Content-Type": "application/json" } },
          );
        }
        return new Response(JSON.stringify({}), { status: 200 });
      }),
    );
    const user = userEvent.setup();
    renderEdit();

    await screen.findByRole("heading", { level: 1, name: "Edit article" });
    await user.click(screen.getByRole("button", { name: "Publish" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("empty body");
  });
});
