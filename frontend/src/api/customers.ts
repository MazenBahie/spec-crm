/** Typed wrappers for every customer-management endpoint. */

import { API_BASE, buildQuery, request } from "./client";
import type {
  Attachment,
  ContactDetail,
  ContactDetailInput,
  Customer,
  CustomerCreate,
  CustomerDetail,
  CustomerStatus,
  CustomerUpdate,
  Interaction,
  InteractionInput,
  Note,
  Page,
} from "../types/customer";

// --------------------------------------------------------------------------- //
// Customers
// --------------------------------------------------------------------------- //
export interface ListCustomersParams {
  q?: string;
  status?: CustomerStatus | "";
  limit?: number;
  offset?: number;
}

export function listCustomers(params: ListCustomersParams = {}): Promise<Page<Customer>> {
  return request<Page<Customer>>(`/customers${buildQuery({ ...params })}`);
}

export function getCustomer(id: string): Promise<CustomerDetail> {
  return request<CustomerDetail>(`/customers/${id}`);
}

export function createCustomer(payload: CustomerCreate): Promise<Customer> {
  return request<Customer>("/customers", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateCustomer(id: string, payload: CustomerUpdate): Promise<Customer> {
  return request<Customer>(`/customers/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function archiveCustomer(id: string): Promise<Customer> {
  return request<Customer>(`/customers/${id}/archive`, { method: "POST" });
}

export function deleteCustomer(id: string): Promise<void> {
  return request<void>(`/customers/${id}`, { method: "DELETE" });
}

// --------------------------------------------------------------------------- //
// Contacts
// --------------------------------------------------------------------------- //
export function listContacts(customerId: string): Promise<ContactDetail[]> {
  return request<ContactDetail[]>(`/customers/${customerId}/contacts`);
}

export function createContact(
  customerId: string,
  payload: ContactDetailInput,
): Promise<ContactDetail> {
  return request<ContactDetail>(`/customers/${customerId}/contacts`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateContact(
  customerId: string,
  contactId: string,
  payload: Partial<ContactDetailInput>,
): Promise<ContactDetail> {
  return request<ContactDetail>(`/customers/${customerId}/contacts/${contactId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function deleteContact(customerId: string, contactId: string): Promise<void> {
  return request<void>(`/customers/${customerId}/contacts/${contactId}`, {
    method: "DELETE",
  });
}

// --------------------------------------------------------------------------- //
// Interactions
// --------------------------------------------------------------------------- //
export function listInteractions(
  customerId: string,
  params: { limit?: number; offset?: number } = {},
): Promise<Page<Interaction>> {
  return request<Page<Interaction>>(
    `/customers/${customerId}/interactions${buildQuery({ ...params })}`,
  );
}

export function createInteraction(
  customerId: string,
  payload: InteractionInput,
): Promise<Interaction> {
  return request<Interaction>(`/customers/${customerId}/interactions`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateInteraction(
  interactionId: string,
  payload: Partial<InteractionInput>,
): Promise<Interaction> {
  return request<Interaction>(`/interactions/${interactionId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function deleteInteraction(interactionId: string): Promise<void> {
  return request<void>(`/interactions/${interactionId}`, { method: "DELETE" });
}

// --------------------------------------------------------------------------- //
// Notes
// --------------------------------------------------------------------------- //
export function listNotes(customerId: string): Promise<Note[]> {
  return request<Note[]>(`/customers/${customerId}/notes`);
}

export function createNote(customerId: string, body: string): Promise<Note> {
  return request<Note>(`/customers/${customerId}/notes`, {
    method: "POST",
    body: JSON.stringify({ body }),
  });
}

export function updateNote(noteId: string, body: string): Promise<Note> {
  return request<Note>(`/notes/${noteId}`, {
    method: "PATCH",
    body: JSON.stringify({ body }),
  });
}

export function deleteNote(noteId: string): Promise<void> {
  return request<void>(`/notes/${noteId}`, { method: "DELETE" });
}

// --------------------------------------------------------------------------- //
// Attachments
// --------------------------------------------------------------------------- //
export function listAttachments(customerId: string): Promise<Attachment[]> {
  return request<Attachment[]>(`/customers/${customerId}/attachments`);
}

export function uploadAttachment(
  customerId: string,
  file: File,
  noteId?: string,
): Promise<Attachment> {
  const form = new FormData();
  form.append("file", file);
  if (noteId) form.append("note_id", noteId);
  return request<Attachment>(`/customers/${customerId}/attachments`, {
    method: "POST",
    body: form,
  });
}

export function deleteAttachment(attachmentId: string): Promise<void> {
  return request<void>(`/attachments/${attachmentId}`, { method: "DELETE" });
}

/** Direct href for downloads — the browser streams it, no fetch needed. */
export function attachmentDownloadUrl(attachmentId: string): string {
  return `${API_BASE}/attachments/${attachmentId}`;
}
