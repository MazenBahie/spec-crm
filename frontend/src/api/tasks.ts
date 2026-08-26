/** Typed wrappers for the agent task and reminder endpoints. */

import { buildQuery, request } from "./client";
import type {
  AgentTask,
  AgentTaskInput,
  AgentTaskStatus,
  AgentTaskUpdateInput,
} from "../types/agent";

export interface ListTasksParams {
  status?: AgentTaskStatus | "";
  /** ISO timestamp; tasks with no reminder are never "due before" anything. */
  due_before?: string;
  limit?: number;
}

export function listTasks(params: ListTasksParams = {}): Promise<AgentTask[]> {
  return request<AgentTask[]>(`/tasks${buildQuery({ ...params })}`);
}

export function createTask(payload: AgentTaskInput): Promise<AgentTask> {
  return request<AgentTask>("/tasks", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateTask(
  id: string,
  payload: AgentTaskUpdateInput,
): Promise<AgentTask> {
  return request<AgentTask>(`/tasks/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

/** Idempotent: completing an already-done task keeps its original timestamp. */
export function completeTask(id: string): Promise<AgentTask> {
  return request<AgentTask>(`/tasks/${id}/complete`, { method: "POST" });
}

export function reopenTask(id: string): Promise<AgentTask> {
  return request<AgentTask>(`/tasks/${id}/reopen`, { method: "POST" });
}

export function deleteTask(id: string): Promise<void> {
  return request<void>(`/tasks/${id}`, { method: "DELETE" });
}
