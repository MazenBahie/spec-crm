/** Mirrors the backend Pydantic `Read` schemas in app/schemas/ticket.py. */

export type TicketStatus =
  | "open"
  | "triaged"
  | "in_progress"
  | "waiting_customer"
  | "resolved"
  | "closed";
export type TicketPriority = "low" | "normal" | "high" | "urgent";
export type TicketEventType =
  | "created"
  | "status_changed"
  | "priority_changed"
  | "category_changed"
  | "assigned"
  | "unassigned"
  | "escalated"
  | "commented"
  | "ai_summary_generated"
  | "ai_category_suggested";

export const TICKET_STATUSES: TicketStatus[] = [
  "open",
  "triaged",
  "in_progress",
  "waiting_customer",
  "resolved",
  "closed",
];
export const TICKET_PRIORITIES: TicketPriority[] = ["low", "normal", "high", "urgent"];

/** Mirrors app.services.tickets.ALLOWED_TRANSITIONS on the backend. */
export const ALLOWED_TRANSITIONS: Record<TicketStatus, TicketStatus[]> = {
  open: ["triaged", "in_progress", "closed"],
  triaged: ["in_progress", "open", "closed"],
  in_progress: ["waiting_customer", "resolved", "triaged", "closed"],
  waiting_customer: ["in_progress", "resolved", "closed"],
  resolved: ["closed", "in_progress"],
  closed: ["open"],
};

export const MAX_ESCALATION_LEVEL = 3;

export interface Agent {
  id: string;
  display_name: string;
  email: string | null;
  is_active: boolean;
  created_at: string;
}

export interface AgentInput {
  display_name: string;
  email?: string | null;
  is_active?: boolean;
}

export interface TicketCategory {
  id: string;
  name: string;
  description: string | null;
  default_priority: TicketPriority;
  is_active: boolean;
  created_at: string;
}

export interface TicketCategoryInput {
  name: string;
  description?: string | null;
  default_priority?: TicketPriority;
  is_active?: boolean;
}

export interface Ticket {
  id: string;
  reference: string;
  customer_id: string;
  category_id: string | null;
  ai_suggested_category_id: string | null;
  assignee_id: string | null;
  subject: string;
  description: string;
  status: TicketStatus;
  priority: TicketPriority;
  escalation_level: number;
  escalated_at: string | null;
  due_at: string | null;
  resolved_at: string | null;
  closed_at: string | null;
  created_at: string;
  updated_at: string;
  is_overdue: boolean;
  ai_summary: string | null;
  ai_summary_generated_at: string | null;
}

export interface TicketDetail extends Ticket {
  customer: {
    id: string;
    display_name: string;
    company: string | null;
    status: string;
  };
  category: TicketCategory | null;
  ai_suggested_category: TicketCategory | null;
  assignee: Agent | null;
}

export interface TicketCreateInput {
  customer_id: string;
  subject: string;
  description?: string;
  category_id?: string | null;
  priority?: TicketPriority | null;
  assignee_id?: string | null;
  due_at?: string | null;
}

export interface TicketUpdateInput {
  subject?: string;
  description?: string;
  category_id?: string | null;
  priority?: TicketPriority;
  due_at?: string | null;
}

export interface TicketEvent {
  id: string;
  ticket_id: string;
  event_type: TicketEventType;
  field: string | null;
  old_value: string | null;
  new_value: string | null;
  comment: string | null;
  actor: string | null;
  created_at: string;
}
