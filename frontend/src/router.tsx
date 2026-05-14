import { createBrowserRouter, Navigate } from "react-router-dom";
import { AppShell } from "./components/layout/AppShell";
import { TicketListPage } from "./pages/TicketListPage";
import { TicketDetailPage } from "./pages/TicketDetailPage";
import { KpiDashboardPage } from "./pages/KpiDashboardPage";
import { AdminCategoriesPage } from "./pages/AdminCategoriesPage";
import { AdminPromptsPage } from "./pages/AdminPromptsPage";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: <Navigate to="/tickets?status=pending" replace /> },
      { path: "tickets", element: <TicketListPage /> },
      { path: "tickets/:id", element: <TicketDetailPage /> },
      { path: "kpi", element: <KpiDashboardPage /> },
      { path: "admin/categories", element: <AdminCategoriesPage /> },
      { path: "admin/prompts", element: <AdminPromptsPage /> },
    ],
  },
]);
