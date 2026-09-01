import { useSyncExternalStore } from "react";
import { Link, Navigate, Outlet, Route, Routes, useNavigate } from "react-router-dom";

import { logout as apiLogout } from "./api/portal";
import { clearPortalSession, getPortalToken, getPortalUser, subscribePortalToken } from "./api/portalAuth";
import PortalArticlePage from "./pages/portal/PortalArticlePage";
import PortalChatPage from "./pages/portal/PortalChatPage";
import PortalKnowledgeBasePage from "./pages/portal/PortalKnowledgeBasePage";
import PortalLoginPage from "./pages/portal/PortalLoginPage";
import PortalNewTicketPage from "./pages/portal/PortalNewTicketPage";
import PortalSignupPage from "./pages/portal/PortalSignupPage";
import PortalTicketDetailPage from "./pages/portal/PortalTicketDetailPage";
import PortalTicketsPage from "./pages/portal/PortalTicketsPage";
import { styles, tokens } from "./components/ui";

/** Deliberately not the agent app's <Nav> -- a fresh, minimal shell instead. */
function PortalShell() {
  const navigate = useNavigate();
  const user = usePortalToken() ? getPortalUser() : null;

  async function handleLogout() {
    try {
      await apiLogout();
    } catch {
      // Best-effort -- clear the local session regardless of whether the
      // server call succeeded (it may already be expired/revoked).
    }
    clearPortalSession();
    navigate("/portal/login");
  }

  return (
    <nav
      style={{
        fontFamily: tokens.font,
        borderBottom: `1px solid ${tokens.border}`,
        padding: "0.75rem 1rem",
        display: "flex",
        gap: "1rem",
        alignItems: "center",
        justifyContent: "space-between",
      }}
    >
      <strong>Customer Portal</strong>
      {user && (
        <span style={{ display: "flex", gap: "1rem", alignItems: "center" }}>
          <Link to="/portal/chat" style={{ color: tokens.accent }}>
            Chat with us
          </Link>
          <span style={{ color: tokens.muted }}>{user.display_name}</span>
          <button type="button" style={styles.button} onClick={() => void handleLogout()}>
            Log out
          </button>
        </span>
      )}
    </nav>
  );
}

function usePortalToken(): string | null {
  return useSyncExternalStore(subscribePortalToken, getPortalToken, getPortalToken);
}

function PortalProtectedRoute() {
  const token = usePortalToken();
  if (!token) return <Navigate to="/portal/login" replace />;
  return <Outlet />;
}

export default function PortalApp() {
  return (
    <>
      <PortalShell />
      <Routes>
        <Route path="login" element={<PortalLoginPage />} />
        <Route path="signup" element={<PortalSignupPage />} />
        {/* Knowledge base browsing needs no portal session -- it lives
            outside PortalProtectedRoute, alongside login/signup. */}
        <Route path="kb" element={<PortalKnowledgeBasePage />} />
        <Route path="kb/:slug" element={<PortalArticlePage />} />
        <Route element={<PortalProtectedRoute />}>
          <Route path="tickets" element={<PortalTicketsPage />} />
          <Route path="tickets/new" element={<PortalNewTicketPage />} />
          <Route path="tickets/:id" element={<PortalTicketDetailPage />} />
          <Route path="chat" element={<PortalChatPage />} />
          <Route index element={<Navigate to="tickets" replace />} />
        </Route>
        <Route path="*" element={<Navigate to="login" replace />} />
      </Routes>
    </>
  );
}
