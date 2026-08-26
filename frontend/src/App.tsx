import { Link, Route, Routes, useLocation } from "react-router-dom";

import CustomerDetailPage from "./pages/CustomerDetailPage";
import CustomerEditPage from "./pages/CustomerEditPage";
import CustomersListPage from "./pages/CustomersListPage";
import HealthPage from "./pages/HealthPage";
import TicketDetailPage from "./pages/TicketDetailPage";
import TicketEditPage from "./pages/TicketEditPage";
import TicketSetupPage from "./pages/TicketSetupPage";
import TicketsListPage from "./pages/TicketsListPage";
import { tokens } from "./components/ui";

const NAV = [
  { to: "/", label: "Health" },
  { to: "/customers", label: "Customers" },
  { to: "/tickets", label: "Tickets" },
];

function Nav() {
  const { pathname } = useLocation();
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
        const active =
          item.to === "/" ? pathname === "/" : pathname.startsWith(item.to);
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
        <Route path="/" element={<HealthPage />} />
        <Route path="/customers" element={<CustomersListPage />} />
        <Route path="/customers/new" element={<CustomerEditPage />} />
        <Route path="/customers/:id" element={<CustomerDetailPage />} />
        <Route path="/customers/:id/edit" element={<CustomerEditPage />} />
        <Route path="/tickets" element={<TicketsListPage />} />
        <Route path="/tickets/new" element={<TicketEditPage />} />
        <Route path="/tickets/setup" element={<TicketSetupPage />} />
        <Route path="/tickets/:id" element={<TicketDetailPage />} />
        <Route path="/tickets/:id/edit" element={<TicketEditPage />} />
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
