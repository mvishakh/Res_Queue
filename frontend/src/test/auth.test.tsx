import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

// The real AuthProvider, with only the Supabase client and the API call replaced.
const auth = vi.hoisted(() => ({
  session: null as null | { user: { id: string }; access_token: string },
}))

vi.mock('../lib/supabase', () => ({
  supabaseConfigured: true,
  supabase: {
    auth: {
      getSession: () => Promise.resolve({ data: { session: auth.session } }),
      onAuthStateChange: () => ({ data: { subscription: { unsubscribe: () => {} } } }),
      signInWithPassword: vi.fn(),
      signOut: vi.fn(),
    },
  },
}))

const apiMock = vi.fn()
vi.mock('../lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../lib/api')>()),
  api: (path: string) => apiMock(path),
}))

import { AuthProvider, useAuth } from '../auth/AuthContext'

function Status() {
  const { status, membership } = useAuth()
  return <p>status:{status}{membership ? ` role:${membership.role}` : ''}</p>
}

function renderProvider() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <AuthProvider><Status /></AuthProvider>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  apiMock.mockReset()
  auth.session = null
})

describe('AuthProvider', () => {
  it('reports signed-out (not stuck loading) when there is no session', async () => {
    renderProvider()
    expect(await screen.findByText('status:signed-out')).toBeInTheDocument()
    expect(apiMock).not.toHaveBeenCalled()
  })

  it('loads the staff profile when a session exists', async () => {
    auth.session = { user: { id: 'u1' }, access_token: 't' }
    apiMock.mockResolvedValue({
      id: 'u1', email: 'o@example.com', full_name: 'Owner',
      memberships: [{ restaurant_id: 'r1', restaurant_name: 'ResQ', restaurant_slug: 'resq', role: 'OWNER', dashboard: 'queue-manager' }],
    })
    renderProvider()
    expect(await screen.findByText('status:signed-in role:OWNER')).toBeInTheDocument()
    expect(apiMock).toHaveBeenCalledWith('/auth/me')
  })

  it('reports no-access for an account without a restaurant', async () => {
    auth.session = { user: { id: 'u2' }, access_token: 't' }
    apiMock.mockResolvedValue({ id: 'u2', email: 'x@example.com', full_name: 'X', memberships: [] })
    renderProvider()
    expect(await screen.findByText('status:no-access')).toBeInTheDocument()
  })
})
