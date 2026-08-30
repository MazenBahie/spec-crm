/** Mirrors the backend Pydantic schemas in app/schemas/portal.py. */

import type { TicketCategory } from "./ticket";

export interface PortalUser {
  id: string;
  customer_id: string;
  email: string;
  display_name: string;
}

export interface PortalAuthResponse {
  token: string;
  expires_at: string;
  portal_user: PortalUser;
}

export interface PortalSignupInput {
  email: string;
  password: string;
  display_name: string;
}

export interface PortalLoginInput {
  email: string;
  password: string;
}

export interface PortalTicketCreateInput {
  subject: string;
  description?: string;
  category_id?: string | null;
}

export interface TicketFeedback {
  id: string;
  ticket_id: string;
  rating: number;
  comment: string | null;
  created_at: string;
  updated_at: string;
}

export interface TicketFeedbackInput {
  rating: number;
  comment?: string | null;
}

// Re-exported so portal pages have one place to import ticket-adjacent types
// from without reaching into ../types/ticket directly.
export type { TicketCategory };
