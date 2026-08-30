import { Link, Navigate, Route, Routes, useLocation } from "react-router-dom";

import CustomerDetailPage from "./pages/CustomerDetailPage";
import CustomerEditPage from "./pages/CustomerEditPage";
import CustomersListPage from "./pages/CustomersListPage";
import DashboardPage from "./pages/DashboardPage";
import HealthPage from "./pages/HealthPage";
import TicketDetailPage from "./pages/TicketDetailPage";
import TicketEditPage from "./pages/TicketEditPage";
import TicketSetupPage from "./pages/TicketSetupPage";
import TicketsListPage from "./pages/TicketsListPage";
import PortalApp from "./PortalApp";
import { tokens } from "./components/ui";

// The dashboard is where a shift starts, so it takes the landing slot; health
// keeps its page, just no longer at the root.
const NAV = [
  { to: "/dashboard", label: "Dashboard" },
  { to: "/customers", label: "Customers" },
  { to: "/tickets", label: "Tickets" },
  { to: "/health", label: "Health" },
];

function Nav() {
  const { pathname } = useLocation();
  // The portal renders its own shell (PortalApp/PortalShell) -- the agent
  // nav must never appear there.
  if (pathname.startsWith("/portal")) return null;
  return (
    <nav
      style={{
        fontFamily: tokens.font,
        borderBottom: `1px solid ${tokens.border}`,
        padding: "0.75rem 1rem",
        display: "flex",
        gap: "1rem",
        alignItems: "center",
      }}
    >
      <strong style={{ marginRight: "0.5rem" }}>CRM</strong>
      {NAV.map((item) => {
        const active = pathname.startsWith(item.to);
        return (
          <Link
            key={item.to}
            to={item.to}
            aria-current={active ? "page" : undefined}
            style={{
              textDecoration: "none",
              color: active ? tokens.accent : tokens.muted,
              fontWeight: active ? 600 : 400,
            }}
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}

export default function App() {
  return (
    <>
      <Nav />
      <Routes>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/health" element={<HealthPage />} />
        <Route path="/customers" element={<CustomersListPage />} />
        <Route path="/customers/new" element={<CustomerEditPage />} />
        <Route path="/customers/:id" element={<CustomerDetailPage />} />
        <Route path="/customers/:id/edit" element={<CustomerEditPage />} />
        <Route path="/tickets" element={<TicketsListPage />} />
        <Route path="/tickets/new" element={<TicketEditPage />} />
        <Route path="/tickets/setup" element={<TicketSetupPage />} />
        <Route path="/tickets/:id" element={<TicketDetailPage />} />
        <Route path="/tickets/:id/edit" element={<TicketEditPage />} />
        <Route path="/portal/*" element={<PortalApp />} />
        <Route
          path="*"
          element={
            <main style={{ fontFamily: tokens.font, padding: "2rem" }}>
              <h1>Not found</h1>
              <Link to="/">Go home</Link>
            </main>
          }
        />
      </Routes>
    </>
  );
}
