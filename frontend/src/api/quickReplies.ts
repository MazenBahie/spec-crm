/** Typed wrappers for the quick-reply (canned response) endpoints.
 *
 * The list is the team library plus the caller's own personal replies. Bodies
 * are stored as templates and rendered at insert time — see
 * `components/dashboard/QuickReplyPicker`.
 */

import { request } from "./client";
import type { QuickReply, QuickReplyInput } from "../types/agent";

export function list(): Promise<QuickReply[]> {
  return request<QuickReply[]>("/quick-replies");
}

/** Ownership follows `scope` and is assigned by the server, never sent. */
export function create(payload: QuickReplyInput): Promise<QuickReply> {
  return request<QuickReply>("/quick-replies", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function update(
  id: string,
  payload: Partial<QuickReplyInput>,
): Promise<QuickReply> {
  return request<QuickReply>(`/quick-replies/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function remove(id: string): Promise<void> {
  return request<void>(`/quick-replies/${id}`, { method: "DELETE" });
}
