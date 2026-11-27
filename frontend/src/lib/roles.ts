import type { Dashboard, StaffRole } from './types'

/** Exactly two staff dashboards. Owners/administrators use the Queue Manager Dashboard. */
export function dashboardFor(role: StaffRole): Dashboard {
  return role === 'WAITER' ? 'waiter' : 'queue-manager'
}

export function homePathFor(role: StaffRole): string {
  return dashboardFor(role) === 'waiter' ? '/waiter' : '/manager'
}

export function canUseDashboard(role: StaffRole, dashboard: Dashboard): boolean {
  return dashboardFor(role) === dashboard
}

export const isOwner = (role: StaffRole | undefined) => role === 'OWNER'

export const ROLE_LABELS: Record<StaffRole, string> = {
  OWNER: 'Owner / Administrator',
  QUEUE_MANAGER: 'Queue Manager',
  WAITER: 'Waiter',
}
