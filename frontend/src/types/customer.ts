/** Mirrors the backend Pydantic `Read` schemas in app/schemas/customer.py. */

export type CustomerStatus = "active" | "archived";
export type ContactKind = "phone" | "email" | "address" | "other";
export type InteractionKind = "call" | "email" | "meeting" | "chat" | "other";

export const CONTACT_KINDS: ContactKind[] = ["phone", "email", "address", "other"];
export const INTERACTION_KINDS: InteractionKind[] = [
  "call",
  "email",
  "meeting",
  "chat",
  "other",
];

export interface Page<T> {
  items: T[];
  total: number;
}

export interface Customer {
  id: string;
  display_name: string;
  company: string | null;
  status: CustomerStatus;
  archived_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface CustomerDetail extends Customer {
  contacts: ContactDetail[];
}

export interface CustomerCreate {
  display_name: string;
  company?: string | null;
}

export interface CustomerUpdate {
  display_name?: string;
  company?: string | null;
  status?: CustomerStatus;
}

export interface ContactDetail {
  id: string;
  customer_id: string;
  kind: ContactKind;
  value: string;
  label: string | null;
  is_primary: boolean;
  created_at: string;
}

export interface ContactDetailInput {
  kind: ContactKind;
  value: string;
  label?: string | null;
  is_primary?: boolean;
}

export interface Interaction {
  id: string;
  customer_id: string;
  kind: InteractionKind;
  subject: string | null;
  body: string;
  occurred_at: string;
  author: string | null;
  created_at: string;
}

export interface InteractionInput {
  kind: InteractionKind;
  subject?: string | null;
  body?: string;
  occurred_at: string;
  author?: string | null;
}

export interface Note {
  id: string;
  customer_id: string;
  body: string;
  created_at: string;
  updated_at: string;
}

export interface Attachment {
  id: string;
  customer_id: string;
  note_id: string | null;
  filename: string;
  content_type: string;
  size_bytes: number;
  created_at: string;
}
