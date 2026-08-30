/**
 * Portal-customer identity.
 *
 * Mirrors `agentContext.ts`'s storage/listener shape, but for a **real**
 * bearer token (never a bare, unverified id): the token comes back from
 * `POST /api/portal/auth/signup` or `/login`, is stored in `localStorage`
 * under its own key, and is sent as `Authorization: Bearer <token>` by
 * `portalClient.ts`. There is no separate "placeholder" note here because
 * this one is the real thing.
 */

import type { PortalUser } from "../types/portal";

const TOKEN_KEY = "portalToken";
const USER_KEY = "portalUser";

const listeners = new Set<() => void>();

let currentToken: string | null = readToken();
let currentUser: PortalUser | null = readUser();

function readToken(): string | null {
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

function readUser(): PortalUser | null {
  try {
    const raw = window.localStorage.getItem(USER_KEY);
    return raw ? (JSON.parse(raw) as PortalUser) : null;
  } catch {
    return null;
  }
}

function emit(): void {
  for (const listener of listeners) listener();
}

export function getPortalToken(): string | null {
  return currentToken;
}

export function getPortalUser(): PortalUser | null {
  return currentUser;
}

export function setPortalSession(token: string, user: PortalUser): void {
  currentToken = token;
  currentUser = user;
  try {
    window.localStorage.setItem(TOKEN_KEY, token);
    window.localStorage.setItem(USER_KEY, JSON.stringify(user));
  } catch {
    // Not persisted across reloads, but usable for this session.
  }
  emit();
}

export function clearPortalSession(): void {
  currentToken = null;
  currentUser = null;
  try {
    window.localStorage.removeItem(TOKEN_KEY);
    window.localStorage.removeItem(USER_KEY);
  } catch {
    // Nothing to clean up.
  }
  emit();
}

/** Subscribe to changes; returns the unsubscribe function. */
export function subscribePortalToken(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** The identifying header, or nothing when no one is logged in. */
export function portalAuthHeaders(): Record<string, string> {
  return currentToken ? { Authorization: `Bearer ${currentToken}` } : {};
}
