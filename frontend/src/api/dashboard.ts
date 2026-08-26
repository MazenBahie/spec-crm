/** Typed wrappers for the agent-dashboard read endpoints.
 *
 * Every call here needs an `X-Agent-Id`, which `client.request` attaches from
 * `agentContext`. Without one the backend answers 401 and the dashboard falls
 * back to asking who is on shift.
 */

import { buildQuery, request } from "./client";
import type { ActivityEvent, DashboardSummary } from "../types/agent";
import type { Customer } from "../types/customer";
import type { Ticket } from "../types/ticket";

export function getSummary(): Promise<DashboardSummary> {
  return request<DashboardSummary>("/dashboard/summary");
}

/** The caller's open tickets, most pressing first. A plain list, not a page. */
export function getQueue(params: { limit?: number } = {}): Promise<Ticket[]> {
  return request<Ticket[]>(`/dashboard/queue${buildQuery({ ...params })}`);
}

export function getRecentCustomers(
  params: { limit?: number } = {},
): Promise<Customer[]> {
  return request<Customer[]>(`/dashboard/recent-customers${buildQuery({ ...params })}`);
}

export function getActivity(params: { limit?: number } = {}): Promise<ActivityEvent[]> {
  return request<ActivityEvent[]>(`/dashboard/activity${buildQuery({ ...params })}`);
}
