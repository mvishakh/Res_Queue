import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthContext, type AuthValue } from '../auth/AuthContext'
import { ToastProvider } from '../components/Toast'
import { canUseDashboard, dashboardFor, homePathFor } from '../lib/roles'
import type { Membership, StaffRole } from '../lib/types'
import { routes } from '../routes'

// Pages fetch from FastAPI; for routing tests the requests simply stay pending,
// except the public menu which returns a small menu.
const apiMock = vi.fn()
vi.mock('../lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../lib/api')>()),
  api: (path: string, opts?: unknown) => apiMock(path, opts),
}))

beforeEach(() => {
  apiMock.mockReset()
  apiMock.mockImplementation((path: string) =>
    path.startsWith('/public/menu/')
      ? Promise.resolve({ restaurant_name: 'Spice Garden', logo_url: null, address: null, currency: 'INR', intro: null, categories: [] })
      : new Promise(() => {}),
  )
})

function membership(role: StaffRole): Membership {
  return { restaurant_id: 'r1', restaurant_name: 'Spice Garden', restaurant_slug: 'spice-garden', role, dashboard: dashboardFor(role) }
}

function auth(role: StaffRole | null): AuthValue {
  const m = role ? membership(role) : null
  return {
    status: role ? 'signed-in' : 'signed-out',
    me: role ? { id: 'u1', email: 'staff@example.com', full_name: 'Staff Member', memberships: [m!] } : null,
    membership: m,
    error: null,
    signIn: vi.fn(),
    signOut: vi.fn(),
    selectRestaurant: vi.fn(),
  }
}

function renderAt(path: string, role: StaffRole | null) {
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <AuthContext.Provider value={auth(role)}>
        <ToastProvider>
          <RouterProvider router={router} />
        </ToastProvider>
      </AuthContext.Provider>
    </QueryClientProvider>,
  )
  return router
}

describe('role → dashboard mapping', () => {
  it('maps owners and queue managers to Dashboard 1 and waiters to Dashboard 2', () => {
    expect(dashboardFor('OWNER')).toBe('queue-manager')
    expect(dashboardFor('QUEUE_MANAGER')).toBe('queue-manager')
    expect(dashboardFor('WAITER')).toBe('waiter')
    expect(homePathFor('WAITER')).toBe('/waiter')
    expect(canUseDashboard('WAITER', 'queue-manager')).toBe(false)
    expect(canUseDashboard('QUEUE_MANAGER', 'waiter')).toBe(false)
  })
})

describe('dashboard redirection after login', () => {
  it('sends a queue manager to the Queue Manager Dashboard', async () => {
    const router = renderAt('/', 'QUEUE_MANAGER')
    expect(await screen.findByRole('heading', { name: 'Dashboard' })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/manager')
  })

  it('sends an owner to the Queue Manager Dashboard with Settings available', async () => {
    const router = renderAt('/', 'OWNER')
    expect(await screen.findByRole('heading', { name: 'Dashboard' })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/manager')
    expect(screen.getAllByRole('link', { name: /Settings/ }).length).toBeGreaterThan(0)
  })

  it('sends a waiter to the Waiter Dashboard', async () => {
    const router = renderAt('/', 'WAITER')
    expect(await screen.findByRole('heading', { name: 'Table Overview' })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/waiter')
  })

  it('redirects a signed-in user away from the login page to their dashboard', async () => {
    const router = renderAt('/login', 'WAITER')
    await screen.findByRole('heading', { name: 'Table Overview' })
    expect(router.state.location.pathname).toBe('/waiter')
  })
})

describe('unauthorized access to dashboard routes', () => {
  it.each(['/', '/manager', '/manager/waiting-list', '/waiter', '/waiter/updates'])('requires sign-in for %s', async (path) => {
    const router = renderAt(path, null)
    expect(await screen.findByRole('heading', { name: 'Smart Queue' })).toBeInTheDocument()
    expect(screen.getByLabelText('Password')).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/login')
  })

  it.each(['/manager', '/manager/register', '/manager/menu', '/manager/analytics', '/manager/settings'])(
    'keeps a waiter out of %s',
    async (path) => {
      const router = renderAt(path, 'WAITER')
      await screen.findByRole('heading', { name: 'Table Overview' })
      expect(router.state.location.pathname).toBe('/waiter')
    },
  )

  it('keeps a queue manager out of the Waiter Dashboard', async () => {
    const router = renderAt('/waiter/availability', 'QUEUE_MANAGER')
    await screen.findByRole('heading', { name: 'Dashboard' })
    expect(router.state.location.pathname).toBe('/manager')
  })

  it('keeps a queue manager out of owner-only Settings', async () => {
    const router = renderAt('/manager/settings', 'QUEUE_MANAGER')
    await screen.findByRole('heading', { name: 'Dashboard' })
    expect(router.state.location.pathname).toBe('/manager')
    expect(screen.queryByRole('link', { name: /Settings/ })).not.toBeInTheDocument()
  })
})

describe('waiter dashboard restrictions', () => {
  it('shows no registration, waiting-list, menu or analytics navigation', async () => {
    renderAt('/waiter', 'WAITER')
    await screen.findByRole('heading', { name: 'Table Overview' })
    const links = screen.getAllByRole('link').map((l) => l.textContent ?? '')
    for (const forbidden of [/Registration/, /Waiting List/, /Menu/, /Analytics/, /Customers/, /Settings/]) {
      expect(links.some((l) => forbidden.test(l))).toBe(false)
    }
  })
})

describe('public digital menu', () => {
  it('opens without signing in', async () => {
    renderAt('/menu/spice-garden', null)
    expect(await screen.findByRole('heading', { name: 'Spice Garden' })).toBeInTheDocument()
    expect(apiMock).toHaveBeenCalledWith('/public/menu/spice-garden', { auth: false })
  })
})
