/**
 * Who is at the keyboard.
 *
 * **Placeholder for real authentication**, matching `backend/app/api/deps.py`:
 * the chosen agent id is kept in `localStorage` and sent as `X-Agent-Id`. There
 * is no credential and no verification — a follow-up auth story replaces both
 * ends at once.
 *
 * There is deliberately no dev default. Agent ids are uuids assigned by the
 * database, so no hard-coded value could ever be right; with nothing stored the
 * dashboard asks who is on shift and saves the answer.
 */

const STORAGE_KEY = "agentId";

const listeners = new Set<() => void>();

/** Cached so `getAgentId` is a cheap, referentially stable store read. */
let current: string | null = read();

function read(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    // Private mode, or storage disabled entirely. Behave as "nobody picked
    // yet" rather than taking the page down.
    return null;
  }
}

function emit(): void {
  for (const listener of listeners) listener();
}

export function getAgentId(): string | null {
  return current;
}

export function setAgentId(id: string): void {
  current = id;
  try {
    window.localStorage.setItem(STORAGE_KEY, id);
  } catch {
    // Not persisted across reloads, but usable for this session.
  }
  emit();
}

export function clearAgentId(): void {
  current = null;
  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Nothing to clean up.
  }
  emit();
}

/** Subscribe to changes; returns the unsubscribe function. */
export function subscribeAgentId(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** The identifying header, or nothing when no agent has been chosen. */
export function agentHeaders(): Record<string, string> {
  return current ? { "X-Agent-Id": current } : {};
}
