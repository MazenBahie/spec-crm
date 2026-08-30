/** Typed wrappers for every customer-portal endpoint. */

import { buildQuery } from "./client";
import { requestPortal } from "./portalClient";
import type { Page } from "../types/customer";
import type { Ticket, TicketEvent } from "../types/ticket";
import type {
  PortalAuthResponse,
  PortalLoginInput,
  PortalSignupInput,
  PortalTicketCreateInput,
  PortalUser,
  TicketFeedback,
  TicketFeedbackInput,
} from "../types/portal";

// --------------------------------------------------------------------------- //
// Auth
// --------------------------------------------------------------------------- //
export function signup(payload: PortalSignupInput): Promise<PortalAuthResponse> {
  return requestPortal<PortalAuthResponse>("/portal/auth/signup", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function login(payload: PortalLoginInput): Promise<PortalAuthResponse> {
  return requestPortal<PortalAuthResponse>("/portal/auth/login", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function logout(): Promise<void> {
  return requestPortal<void>("/portal/auth/logout", { method: "POST" });
}

export function getMe(): Promise<PortalUser> {
  return requestPortal<PortalUser>("/portal/auth/me");
}

// --------------------------------------------------------------------------- //
// Tickets
// --------------------------------------------------------------------------- //
export function listPortalTickets(
  params: { limit?: number; offset?: number } = {},
): Promise<Page<Ticket>> {
  return requestPortal<Page<Ticket>>(`/portal/tickets${buildQuery({ ...params })}`);
}

export function createPortalTicket(payload: PortalTicketCreateInput): Promise<Ticket> {
  return requestPortal<Ticket>("/portal/tickets", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getPortalTicket(id: string): Promise<Ticket> {
  return requestPortal<Ticket>(`/portal/tickets/${id}`);
}

export function listPortalTicketEvents(id: string): Promise<TicketEvent[]> {
  return requestPortal<TicketEvent[]>(`/portal/tickets/${id}/events`);
}

// --------------------------------------------------------------------------- //
// Feedback
// --------------------------------------------------------------------------- //
export function getFeedback(ticketId: string): Promise<TicketFeedback | null> {
  return requestPortal<TicketFeedback | null>(`/portal/tickets/${ticketId}/feedback`);
}

export function submitFeedback(
  ticketId: string,
  payload: TicketFeedbackInput,
): Promise<TicketFeedback> {
  return requestPortal<TicketFeedback>(`/portal/tickets/${ticketId}/feedback`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
