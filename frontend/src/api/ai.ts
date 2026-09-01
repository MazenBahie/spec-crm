/** Typed wrappers for the AI-features endpoints (stories 09-13 each add to
 * this file rather than each starting a new one). */

import { buildQuery, request } from "./client";
import type { ArticleSummary } from "../types/knowledgeBase";
import type { Ticket, TicketDetail } from "../types/ticket";

// --------------------------------------------------------------------------- //
// Story 09 -- ticket summaries
// --------------------------------------------------------------------------- //
/** Read-only view of a ticket's persisted summary, without a POST.
 *
 * There is no dedicated GET endpoint for this -- the two fields already ride
 * on `GET /tickets/{id}`. This wrapper exists so a component that only cares
 * about the summary can ask for it by name; it costs the same one network
 * call `getTicket` does, not an extra one.
 */
export function getTicketSummary(
  ticketId: string,
): Promise<Pick<Ticket, "ai_summary" | "ai_summary_generated_at">> {
  return request<Ticket>(`/tickets/${ticketId}`);
}

export function regenerateTicketSummary(ticketId: string): Promise<Ticket> {
  return request<Ticket>(`/tickets/${ticketId}/ai/summary`, { method: "POST" });
}

// --------------------------------------------------------------------------- //
// Story 10 -- suggested replies
// --------------------------------------------------------------------------- //
interface SuggestedReplyResponse {
  draft: string;
}

/** Draft a reply from the ticket's thread. Never sends anything -- the
 * caller is responsible for putting `draft` in front of the agent for review
 * before it goes anywhere near the existing send path. */
export function suggestReply(ticketId: string): Promise<string> {
  return request<SuggestedReplyResponse>(`/tickets/${ticketId}/ai/suggested-reply`, {
    method: "POST",
  }).then((res) => res.draft);
}

// --------------------------------------------------------------------------- //
// Story 11 -- automatic categorization
// --------------------------------------------------------------------------- //
export function recomputeSuggestedCategory(ticketId: string): Promise<TicketDetail> {
  return request<TicketDetail>(`/tickets/${ticketId}/ai/suggested-category`, {
    method: "POST",
  });
}

// --------------------------------------------------------------------------- //
// Story 12 -- suggested solutions
// --------------------------------------------------------------------------- //
export function getSuggestedSolutions(
  ticketId: string,
  params: { limit?: number } = {},
): Promise<ArticleSummary[]> {
  return request<ArticleSummary[]>(
    `/tickets/${ticketId}/ai/suggested-solutions${buildQuery({ ...params })}`,
  );
}
