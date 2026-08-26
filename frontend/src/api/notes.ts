/** Typed wrappers for the internal ticket-note endpoints.
 *
 * Internal notes are agent-to-agent and are never delivered to the customer —
 * they are a separate resource from the channel message thread in
 * `api/channels.ts`, backed by a separate table with no driver behind it.
 */

import { buildQuery, request } from "./client";
import type { TicketNote } from "../types/agent";
import type { Page } from "../types/customer";

export function listNotes(
  ticketId: string,
  params: { limit?: number; offset?: number } = {},
): Promise<Page<TicketNote>> {
  return request<Page<TicketNote>>(`/tickets/${ticketId}/notes${buildQuery({ ...params })}`);
}

export function addNote(ticketId: string, body: string): Promise<TicketNote> {
  return request<TicketNote>(`/tickets/${ticketId}/notes`, {
    method: "POST",
    body: JSON.stringify({ body }),
  });
}
