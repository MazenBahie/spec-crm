/** Typed wrappers for every ticket-management endpoint. */

import { buildQuery, request } from "./client";
import type { Page } from "../types/customer";
import type {
  Agent,
  AgentInput,
  Ticket,
  TicketCategory,
  TicketCategoryInput,
  TicketCreateInput,
  TicketDetail,
  TicketEvent,
  TicketPriority,
  TicketStatus,
  TicketUpdateInput,
} from "../types/ticket";

// --------------------------------------------------------------------------- //
// Tickets
// --------------------------------------------------------------------------- //
export interface ListTicketsParams {
  q?: string;
  status?: TicketStatus | "";
  priority?: TicketPriority | "";
  customer_id?: string;
  assignee_id?: string;
  category_id?: string;
  unassigned?: boolean;
  limit?: number;
  offset?: number;
}

export function listTickets(params: ListTicketsParams = {}): Promise<Page<Ticket>> {
  const { unassigned, ...rest } = params;
  return request<Page<Ticket>>(
    `/tickets${buildQuery({ ...rest, unassigned: unassigned ? "true" : undefined })}`,
  );
}

export function getTicket(id: string): Promise<TicketDetail> {
  return request<TicketDetail>(`/tickets/${id}`);
}

export function createTicket(payload: TicketCreateInput): Promise<Ticket> {
  return request<Ticket>("/tickets", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateTicket(id: string, payload: TicketUpdateInput): Promise<Ticket> {
  return request<Ticket>(`/tickets/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function deleteTicket(id: string): Promise<void> {
  return request<void>(`/tickets/${id}`, { method: "DELETE" });
}

export function changeTicketStatus(
  id: string,
  status: TicketStatus,
  options: { comment?: string; actor?: string } = {},
): Promise<Ticket> {
  return request<Ticket>(`/tickets/${id}/status`, {
    method: "POST",
    body: JSON.stringify({ status, ...options }),
  });
}

export function assignTicket(
  id: string,
  assigneeId: string | null,
  options: { actor?: string } = {},
): Promise<Ticket> {
  return request<Ticket>(`/tickets/${id}/assignment`, {
    method: "POST",
    body: JSON.stringify({ assignee_id: assigneeId, ...options }),
  });
}

export function escalateTicket(
  id: string,
  options: { comment?: string; actor?: string; raise_priority?: boolean } = {},
): Promise<Ticket> {
  return request<Ticket>(`/tickets/${id}/escalate`, {
    method: "POST",
    body: JSON.stringify(options),
  });
}

export function listCustomerTickets(
  customerId: string,
  params: { limit?: number; offset?: number } = {},
): Promise<Page<Ticket>> {
  return request<Page<Ticket>>(`/customers/${customerId}/tickets${buildQuery({ ...params })}`);
}

// --------------------------------------------------------------------------- //
// Ticket events
// --------------------------------------------------------------------------- //
export function listTicketEvents(
  ticketId: string,
  params: { limit?: number; offset?: number } = {},
): Promise<Page<TicketEvent>> {
  return request<Page<TicketEvent>>(
    `/tickets/${ticketId}/events${buildQuery({ ...params })}`,
  );
}

export function addTicketComment(
  ticketId: string,
  comment: string,
  actor?: string,
): Promise<TicketEvent> {
  return request<TicketEvent>(`/tickets/${ticketId}/events`, {
    method: "POST",
    body: JSON.stringify({ comment, actor }),
  });
}

// --------------------------------------------------------------------------- //
// Ticket categories
// --------------------------------------------------------------------------- //
export function listCategories(params: { activeOnly?: boolean } = {}): Promise<TicketCategory[]> {
  return request<TicketCategory[]>(
    `/ticket-categories${buildQuery({ active_only: params.activeOnly ? "true" : undefined })}`,
  );
}

export function createCategory(payload: TicketCategoryInput): Promise<TicketCategory> {
  return request<TicketCategory>("/ticket-categories", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateCategory(
  id: string,
  payload: Partial<TicketCategoryInput>,
): Promise<TicketCategory> {
  return request<TicketCategory>(`/ticket-categories/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function deleteCategory(id: string): Promise<void> {
  return request<void>(`/ticket-categories/${id}`, { method: "DELETE" });
}

// --------------------------------------------------------------------------- //
// Agents
// --------------------------------------------------------------------------- //
export function listAgents(params: { activeOnly?: boolean } = {}): Promise<Agent[]> {
  return request<Agent[]>(
    `/agents${buildQuery({ active_only: params.activeOnly ? "true" : undefined })}`,
  );
}

export function createAgent(payload: AgentInput): Promise<Agent> {
  return request<Agent>("/agents", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateAgent(id: string, payload: Partial<AgentInput>): Promise<Agent> {
  return request<Agent>(`/agents/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function deactivateAgent(id: string): Promise<Agent> {
  return request<Agent>(`/agents/${id}`, { method: "DELETE" });
}
