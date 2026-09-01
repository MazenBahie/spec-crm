/** Mirrors the backend Pydantic schemas in app/schemas/chatbot.py. */

export type ChatbotRole = "user" | "assistant";

export interface ChatbotSession {
  id: string;
  portal_user_id: string;
  created_at: string;
  updated_at: string;
}

export interface ChatbotMessage {
  id: string;
  session_id: string;
  role: ChatbotRole;
  content: string;
  created_at: string;
}

export interface ChatbotMessageInput {
  content: string;
}

export interface ChatTurn {
  user_message: ChatbotMessage;
  assistant_message: ChatbotMessage;
}
