import type { RouteObject } from 'react-router'
import { RequireAuth, RequireDashboard, RequireOwner, RoleRedirect } from './auth/guards'
import { FullPageMessage } from './components/ui'
import { QueueManagerLayout } from './layouts/QueueManagerLayout'
import { WaiterLayout } from './layouts/WaiterLayout'
import { LoginPage } from './pages/LoginPage'
import { PublicMenuPage } from './pages/PublicMenuPage'
import { AllocationsPage } from './pages/manager/AllocationsPage'
import { AnalyticsPage } from './pages/manager/AnalyticsPage'
import { CustomersPage } from './pages/manager/CustomersPage'
import { DashboardPage } from './pages/manager/DashboardPage'
import { MenuPage } from './pages/manager/MenuPage'
import { RegisterPage } from './pages/manager/RegisterPage'
import { SettingsPage } from './pages/manager/SettingsPage'
import { TablesPage } from './pages/manager/TablesPage'
import { WaitingListPage } from './pages/manager/WaitingListPage'
import { WaiterAvailabilityPage, WaiterProfilePage, WaiterTablesPage, WaiterUpdatesPage } from './pages/waiter/WaiterPages'

/**
 * One application, exactly two staff dashboards:
 *   /manager/*  Dashboard 1 — Queue Manager (Queue Managers, Owners/Administrators)
 *   /waiter/*   Dashboard 2 — Waiter
 * plus the shared login and the public digital menu page (not a dashboard).
 */
export const routes: RouteObject[] = [
  { path: '/login', element: <LoginPage /> },
  { path: '/menu/:slug', element: <PublicMenuPage /> },
  { path: '/', element: <RequireAuth><RoleRedirect /></RequireAuth> },
  {
    path: '/manager',
    element: (
      <RequireAuth>
        <RequireDashboard dashboard="queue-manager"><QueueManagerLayout /></RequireDashboard>
      </RequireAuth>
    ),
    children: [
      { index: true, element: <DashboardPage /> },
      { path: 'register', element: <RegisterPage /> },
      { path: 'waiting-list', element: <WaitingListPage /> },
      { path: 'tables', element: <TablesPage /> },
      { path: 'customers', element: <CustomersPage /> },
      { path: 'menu', element: <MenuPage /> },
      { path: 'allocations', element: <AllocationsPage /> },
      { path: 'analytics', element: <AnalyticsPage /> },
      { path: 'settings', element: <RequireOwner><SettingsPage /></RequireOwner> },
    ],
  },
  {
    path: '/waiter',
    element: (
      <RequireAuth>
        <RequireDashboard dashboard="waiter"><WaiterLayout /></RequireDashboard>
      </RequireAuth>
    ),
    children: [
      { index: true, element: <WaiterTablesPage /> },
      { path: 'availability', element: <WaiterAvailabilityPage /> },
      { path: 'updates', element: <WaiterUpdatesPage /> },
      { path: 'profile', element: <WaiterProfilePage /> },
    ],
  },
  { path: '*', element: <FullPageMessage title="Page not found"><a href="/" className="text-brand-700 underline">Go to your dashboard</a></FullPageMessage> },
]
