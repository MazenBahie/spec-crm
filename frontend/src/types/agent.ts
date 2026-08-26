/** Mirrors the backend Pydantic `Read` schemas in app/schemas/agent.py. */

// `Agent` itself belongs to the ticket story — re-exported here so dashboard
// code has one import, without a second, drifting definition.
export type { Agent } from "./ticket";

export type AgentTaskStatus = "open" | "done";
export type QuickReplyScope = "personal" | "team";
export type ActivityEventType =
  | "ticket.assigned"
  | "ticket.status_changed"
  | "ticket.replied"
  | "note.added"
  | "mention";

export const QUICK_REPLY_SCOPES: QuickReplyScope[] = ["personal", "team"];

export interface AgentTask {
  id: string;
  agent_id: string;
  title: string;
  notes: string | null;
  status: AgentTaskStatus;
  remind_at: string | null;
  ticket_id: string | null;
  customer_id: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface AgentTaskInput {
  title: string;
  notes?: string | null;
  remind_at?: string | null;
  ticket_id?: string | null;
  customer_id?: string | null;
}

export interface AgentTaskUpdateInput {
  title?: string;
  notes?: string | null;
  remind_at?: string | null;
  status?: AgentTaskStatus;
}

export interface QuickReply {
  id: string;
  scope: QuickReplyScope;
  owner_agent_id: string | null;
  shortcut: string | null;
  title: string;
  /** The unrendered template — tokens are expanded at insert time. */
  body: string;
  created_at: string;
  updated_at: string;
}

export interface QuickReplyInput {
  scope: QuickReplyScope;
  title: string;
  body: string;
  shortcut?: string | null;
}

export interface ActivityEvent {
  id: string;
  event_type: ActivityEventType;
  agent_id: string | null;
  ticket_id: string | null;
  customer_id: string | null;
  payload: Record<string, unknown> | null;
  mentions: string[];
  created_at: string;
}

export interface TicketNote {
  id: string;
  ticket_id: string;
  author_agent_id: string | null;
  author_display_name: string | null;
  body: string;
  created_at: string;
}

export interface DashboardSummary {
  open_assigned: number;
  overdue: number;
  tasks_due_today: number;
  unread_mentions: number;
}
