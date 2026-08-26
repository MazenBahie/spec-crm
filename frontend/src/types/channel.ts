/** Mirrors the backend Pydantic `Read` schemas in app/schemas/channel.py. */

export type ChannelSlug = "email" | "whatsapp" | "live_chat" | "sms" | "web_form";
export type MessageDirection = "inbound" | "outbound";
export type MessageStatus = "queued" | "sent" | "delivered" | "failed" | "received";

/** The catalogue is fixed — see app.models.channel.CHANNEL_CATALOGUE. */
export const CHANNEL_SLUGS: ChannelSlug[] = [
  "email",
  "whatsapp",
  "live_chat",
  "sms",
  "web_form",
];

export interface Channel {
  id: string;
  slug: ChannelSlug;
  display_name: string;
  is_enabled: boolean;
  config: Record<string, unknown> | null;
  created_at: string;
}

export interface ChannelUpdateInput {
  is_enabled?: boolean;
  config?: Record<string, unknown> | null;
}

export interface ChannelMessage {
  id: string;
  ticket_id: string;
  channel_id: string;
  channel_slug: ChannelSlug;
  customer_id: string | null;
  direction: MessageDirection;
  status: MessageStatus;
  body: string;
  provider_message_id: string | null;
  error_reason: string | null;
  created_at: string;
}

export interface ChannelMessageInput {
  channel_slug: ChannelSlug;
  body: string;
}
