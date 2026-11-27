import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router'
import { FullPageMessage, Spinner } from '../components/ui'
import { canUseDashboard, homePathFor, isOwner } from '../lib/roles'
import type { Dashboard } from '../lib/types'
import { useAuth } from './AuthContext'

/** Signed-in staff only. Unauthenticated visitors are sent to the login page. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { status, error, signOut } = useAuth()
  const location = useLocation()
  if (status === 'loading') return <FullPageMessage><Spinner label="Loading your account…" /></FullPageMessage>
  if (status === 'signed-out') return <Navigate to="/login" replace state={{ from: location.pathname }} />
  if (status === 'no-access')
    return (
      <FullPageMessage title="No restaurant access">
        This account is not assigned to a restaurant. Ask the restaurant owner to add you as staff.
        <button className="mt-4 text-brand-700 underline" onClick={() => signOut()}>Sign out</button>
      </FullPageMessage>
    )
  if (status === 'error') return <FullPageMessage title="Something went wrong">{error}</FullPageMessage>
  return <>{children}</>
}

/** Each role can open only its own dashboard; anything else redirects home. */
export function RequireDashboard({ dashboard, children }: { dashboard: Dashboard; children: ReactNode }) {
  const { membership } = useAuth()
  if (!membership) return null
  if (!canUseDashboard(membership.role, dashboard)) return <Navigate to={homePathFor(membership.role)} replace />
  return <>{children}</>
}

export function RequireOwner({ children }: { children: ReactNode }) {
  const { membership } = useAuth()
  if (!isOwner(membership?.role)) return <Navigate to="/manager" replace />
  return <>{children}</>
}

/** "/" — send staff to the dashboard for their role. */
export function RoleRedirect() {
  const { membership } = useAuth()
  if (!membership) return null
  return <Navigate to={homePathFor(membership.role)} replace />
}
