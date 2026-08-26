/** Typed wrappers for every communication-channel endpoint. */

import { buildQuery, request } from "./client";
import type { Page } from "../types/customer";
import type {
  Channel,
  ChannelMessage,
  ChannelMessageInput,
  ChannelSlug,
  ChannelUpdateInput,
} from "../types/channel";

// --------------------------------------------------------------------------- //
// Channel catalogue
// --------------------------------------------------------------------------- //
export function listChannels(params: { enabledOnly?: boolean } = {}): Promise<Channel[]> {
  return request<Channel[]>(
    `/channels${buildQuery({ enabled_only: params.enabledOnly ? "true" : undefined })}`,
  );
}

export function updateChannel(
  slug: ChannelSlug,
  payload: ChannelUpdateInput,
): Promise<Channel> {
  return request<Channel>(`/channels/${slug}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

// --------------------------------------------------------------------------- //
// Ticket message thread
// --------------------------------------------------------------------------- //
export function listTicketMessages(
  ticketId: string,
  params: { limit?: number; offset?: number } = {},
): Promise<Page<ChannelMessage>> {
  return request<Page<ChannelMessage>>(
    `/tickets/${ticketId}/messages${buildQuery({ ...params })}`,
  );
}

/**
 * Send an outbound reply. Resolves even when delivery failed — check
 * `status`/`error_reason` on the returned message rather than catching.
 */
export function sendTicketMessage(
  ticketId: string,
  payload: ChannelMessageInput,
): Promise<ChannelMessage> {
  return request<ChannelMessage>(`/tickets/${ticketId}/messages`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
