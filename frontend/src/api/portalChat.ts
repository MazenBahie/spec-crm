/** Typed wrappers for the customer-portal AI chatbot endpoints. */

import { requestPortal } from "./portalClient";
import type { ChatbotMessage, ChatbotMessageInput, ChatbotSession, ChatTurn } from "../types/chatbot";

export function startChatSession(): Promise<ChatbotSession> {
  return requestPortal<ChatbotSession>("/portal/chat/sessions", { method: "POST" });
}

export function listChatMessages(sessionId: string): Promise<ChatbotMessage[]> {
  return requestPortal<ChatbotMessage[]>(`/portal/chat/sessions/${sessionId}/messages`);
}

export function sendChatMessage(sessionId: string, payload: ChatbotMessageInput): Promise<ChatTurn> {
  return requestPortal<ChatTurn>(`/portal/chat/sessions/${sessionId}/messages`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
